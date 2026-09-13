"""Local observations of free routes; never stores credentials or model output."""

import copy
import hashlib
import json
import threading
import time
from pathlib import Path

from .storage import write_json


RECOVERABLE_CODES = {"stream_error", "stream_interrupted", "stream_timeout", "model_timeout",
                     "model_connection", "invalid_response_json", "invalid_stream_json",
                     "invalid_response_shape", "invalid_tool_envelope", "empty_response", "unsupported_tool",
                     "http_408", "http_429", "http_500", "http_502", "http_503", "http_504"}
MAX_HANDOFFS = 2


def automatic(task, role):
    return (not task.get("demo") and task.get("execution", {}).get("mode") in {"delegate", "remote"}
            and bool(task.get("route")) and role in {"worker", "reviewer"})


def observe_task(pool,task,run_id):
    if task.get('demo') or task.get('metrics_cancelled'):return
    groups={}
    for request in task.get('request_metrics',[]):
        if request.get('run_id')!=run_id or request.get('purpose')=='probe' or not request.get('dispatched'):continue
        role,model=request['role'],request['model']
        if role not in {'worker','reviewer'}:continue
        signals=groups.setdefault((role,model),{})
        if request.get('error_code') in {'invalid_tool_envelope','unsupported_tool','output_limit','invalid_response_json','invalid_stream_json','invalid_response_shape'}:
            signals['invalid_output']=signals.get('invalid_output',0)+1
    for event in task.get('events',[]):
        if event.get('run_id')!=run_id:continue
        actor=event.get('actor') or {};key=(actor.get('role'),actor.get('model'))
        if key not in groups:continue
        signals=groups[key];kind=event['kind'];title=event['title'];detail=event.get('detail') or {}
        fields=[]
        if kind=='tool' and isinstance(detail,dict) and 'arguments' in detail:
            fields.append('valid_calls')
            if title in {'write file','replace text','replace lines'}:fields.append('edits')
        if kind=='checks' and isinstance(detail,dict) and detail.get('passed'):fields.append('checks_passed')
        if kind=='checkpoint':fields.append('checkpoints')
        if kind=='review' and isinstance(detail,dict) and detail.get('decision') in {'APPROVE','REQUEST_CHANGES','TAKE_OVER'}:fields.append('reviews_completed')
        if kind=='tool_error' and isinstance(detail,dict) and detail.get('code')=='invalid_tool_arguments':fields.append('invalid_output')
        for field in fields:signals[field]=signals.get(field,0)+1
    for (role,model),signals in groups.items():
        # An outage with no observed work is not a model-quality sample.
        if not any(signals.values()):continue
        config=task.get('providers',{}).get(role) or {}
        endpoint=(task.get('route') or {}).get('base_url') or config.get('base_url')
        if endpoint:pool.record_outcome(endpoint,model,role,run_id,task['id'],signals)


class FreeModelPool:
    def __init__(self, directory):
        self.path = Path(directory) / "model-health.json"
        self.lock = threading.RLock()
        self.revision = 0
        try:
            self.records = json.loads(self.path.read_text())
            if not isinstance(self.records, dict):
                self.records = {}
        except (OSError, ValueError):
            self.records = {}

    @staticmethod
    def key(endpoint, model):
        return hashlib.sha256((endpoint.replace("localhost", "127.0.0.1").rstrip("/") + "\n" + model).encode()).hexdigest()

    def observation(self, endpoint, model):
        with self.lock:
            record = copy.deepcopy(self.records.get(self.key(endpoint, model), {}))
            provider = self.records.get(self.key(endpoint, self.provider_key(model)), {})
            if provider.get("retry_at", 0) > time.time():
                record.update(retry_at=max(record.get("retry_at", 0), provider["retry_at"]),
                              cooldown_scope="provider", retry_known=provider.get("retry_known", False), last_error=provider.get("last_error", ""))
        record["cooling_down"] = record.get("retry_at", 0) > time.time()
        history=[item for item in record.pop('outcomes',[]) if item.get('time',0)>=time.time()-30*86400]
        record['role_evidence']={role:{'samples':len([h for h in history if h['role']==role]),
            **{key:sum(h.get(key,0) for h in history if h['role']==role) for key in ('valid_calls','edits','checks_passed','checkpoints','reviews_completed','invalid_output','accepted')},
            'last_observed':max((h['time'] for h in history if h['role']==role),default=None)} for role in ('worker','reviewer')}
        return record

    @staticmethod
    def provider_key(model):
        return "\0provider/" + model.split("/", 1)[0]

    def record(self, endpoint, model, role, *, error=None, seconds=None, probe=False):
        with self.lock:
            cooldown = getattr(error, "code", None) == "gateway_cooldown"
            scope = getattr(error, "scope", None)
            key = self.key(endpoint, self.provider_key(model) if cooldown and scope == "provider" else model)
            record = self.records.setdefault(key, {})
            record["updated_at"] = time.time()
            if cooldown:
                record.update(retry_at=time.time() + min(86400, max(1, error.retry_after or 120)),
                              cooldown_scope=scope, retry_known=error.retry_after is not None, last_error=str(error)[:500])
            elif error is not None:
                record.pop("cooldown_scope", None)
                record.pop("retry_known", None)
                failures = record.get("failures", 0) + 1
                record.update(failures=failures, retry_at=time.time() + min(3600, 900 * 2 ** min(failures - 1, 2)),
                              last_error=str(error)[:500])
            else:
                record.update(retry_at=0, last_error="")
                record.pop("cooldown_scope", None)
                record.pop("retry_known", None)
                if probe:
                    record["tool_check_passed"] = True
                    record['tool_check_at'] = time.time()
                else:
                    record["failures"] = 0
                    field = role + "_responses"
                    record[field] = record.get(field, 0) + 1
                    if seconds is not None:
                        field = role + "_seconds"
                        record[field] = round(record.get(field, seconds) * .7 + seconds * .3, 3)
            # Retain a bounded history; missing catalog entries never become candidates.
            if len(self.records) > 2000:
                self.records = dict(sorted(self.records.items(), key=lambda item: item[1].get("updated_at", 0))[-2000:])
            write_json(self.path, self.records)
            self.revision += 1

    def rank(self, endpoint, model, role, preferred=None):
        health = self.observation(endpoint, model["id"])
        evidence=health['role_evidence'].get(role,{})
        enough=evidence.get('samples',0)>=3
        successes=evidence.get('checkpoints',0) if role=='worker' else evidence.get('reviews_completed',0)
        invalid=evidence.get('invalid_output',0)
        tier=1 if enough and invalid>=3 and invalid>successes else -1 if enough and successes>=3 and invalid==0 else 0
        # Observed compatibility first. Metadata only breaks ties; it is not a quality rating.
        return (tier, model["id"] != preferred, -min(evidence.get('accepted',0),3) if enough else 0, -min(health.get(role + "_responses", 0), 1),
                -(health.get("tool_check_passed") is True),
                -(model.get("reasoning") is True) if role == "reviewer" else 0,
                -min(model.get("context_length") or 0, 65536) if role == "reviewer" else 0,
                health.get(role + "_seconds", float("inf")), model["id"])

    def record_outcome(self, endpoint, model, role, run_id, task_id, signals):
        """One bounded, idempotent observation per role/model/run; no raw output."""
        if role not in {'worker','reviewer'}:return
        with self.lock:
            record=self.records.setdefault(self.key(endpoint,model),{})
            history=record.setdefault('outcomes',[])
            identity=hashlib.sha256((run_id+'\n'+role).encode()).hexdigest()
            item={'id':identity,'task':hashlib.sha256(task_id.encode()).hexdigest(),'role':role,'time':time.time(),
                  **{k:max(0,int(signals.get(k,0))) for k in ('valid_calls','edits','checks_passed','checkpoints','reviews_completed','invalid_output','accepted')}}
            history[:]=[h for h in history if h.get('id')!=identity and h.get('time',0)>=time.time()-30*86400]+[item]
            record['outcomes']=history[-64:];record['updated_at']=time.time();record['outcome_schema']=1
            if len(self.records)>2000:self.records=dict(sorted(self.records.items(),key=lambda item:item[1].get('updated_at',0))[-2000:])
            write_json(self.path,self.records);self.revision+=1

    def record_acceptance(self, endpoint, model, role, task_id, run_id):
        identity=hashlib.sha256((run_id+'\n'+role).encode()).hexdigest()
        task_key=hashlib.sha256(task_id.encode()).hexdigest()
        with self.lock:
            record=self.records.get(self.key(endpoint,model),{})
            for item in record.get('outcomes',[]):
                if item['id']==identity and item['task']==task_key:
                    item['accepted']=1
                    write_json(self.path,self.records);self.revision+=1
                    break
