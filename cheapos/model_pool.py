"""Local observations of free routes; never stores credentials or model output."""

import copy
import hashlib
import json
import threading
import time
from pathlib import Path

from .storage import write_json
from . import route_health


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
    provenance={}
    for request in task.get('request_metrics',[]):
        if request.get('run_id')!=run_id or request.get('purpose')=='probe' or not request.get('dispatched'):continue
        role,model=request['role'],request['model']
        if role not in {'worker','reviewer'}:continue
        scope=request.get('dispatch_scope')
        if scope and scope.get('role')==role and scope.get('model')==model:
            provenance.setdefault((role,model),set()).add((scope['base_url'],scope['connection_revision']))
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
        scopes=provenance.get((role,model),set())
        if len(scopes)==1:
            endpoint,revision=next(iter(scopes));pool.record_outcome(endpoint,model,role,run_id,task['id'],signals,revision)
        elif not scopes and (not task.get('access_policy') or task['access_policy'].get('base_url') != endpoint) and endpoint:
            pool.record_outcome(endpoint,model,role,run_id,task['id'],signals)


class FreeModelPool:
    def __init__(self, directory):
        self.path = Path(directory) / "model-health.json"
        self.lock = threading.RLock()
        self.revision = 0
        self.inflight_probes = {}
        try:
            self.records = json.loads(self.path.read_text())
            if not isinstance(self.records, dict):
                self.records = {}
        except (OSError, ValueError):
            self.records = {}

    @staticmethod
    def key(endpoint, model, connection_revision=None):
        return hashlib.sha256((endpoint.replace("localhost", "127.0.0.1").rstrip("/") + "\n" + model + ("\nconnection:"+connection_revision if connection_revision is not None else "")).encode()).hexdigest()

    def observation(self, endpoint, model, connection_revision=None):
        with self.lock:
            record = copy.deepcopy(self.records.get(self.key(endpoint, model, connection_revision), {}))
            connection = self.records.get(self.key(endpoint, '\0connection', connection_revision), {})
            provider = self.records.get(self.key(endpoint, self.provider_key(model), connection_revision), {})
            if provider.get("retry_at", 0) > time.time():
                record.update(retry_at=max(record.get("retry_at", 0), provider["retry_at"]),
                              cooldown_scope="provider", retry_known=provider.get("retry_known", False), last_error=provider.get("last_error", ""), failure=provider.get("failure"))
            if connection.get('retry_at', 0) > time.time():
                record.update(retry_at=max(record.get('retry_at',0),connection['retry_at']), cooldown_scope=connection.get('cooldown_scope','connection'),
                              retry_known=connection.get('retry_known', False), last_error=connection.get('last_error', ''),
                              failure=connection.get('failure'))
        record["cooling_down"] = record.get("retry_at", 0) > time.time()
        history=[item for item in record.pop('outcomes',[]) if item.get('time',0)>=time.time()-30*86400 and item.get('connection_revision')==connection_revision]
        completed=[item for item in record.pop('completions',[]) if item.get('time',0)>=time.time()-30*86400 and item.get('connection_revision')==connection_revision]
        record['role_evidence']={role:{'samples':len([h for h in history if h['role']==role]),
            **{key:sum(h.get(key,0) for h in history if h['role']==role) for key in ('valid_calls','edits','checks_passed','checkpoints','reviews_completed','invalid_output','accepted')},
            'last_observed':max((h['time'] for h in history if h['role']==role),default=None)} for role in ('worker','reviewer')}
        for role in ('worker','reviewer'):
            values=[c for c in completed if c['role']==role]
            record['role_evidence'][role].update(completion_samples=len(values),
                completed=sum(c.get('verdict')!='disproved' for c in values),
                independently_validated=sum(c.get('verdict')=='validated' for c in values),
                independently_disproved=sum(c.get('verdict')=='disproved' for c in values),
                human_integrated=sum(c.get('human_integrated') is True for c in values))
        return record

    @staticmethod
    def provider_key(model):
        return "\0provider/" + model.split("/", 1)[0]

    def record(self, endpoint, model, role, *, error=None, seconds=None, probe=False, connection_revision=None, probe_identity=None, failure_context=None):
        with self.lock:
            failure = route_health.classify(error, failure_context) if error is not None else None
            if failure and (failure['category'] == 'cancelled' or failure['scope'] == 'request'): return
            cooldown = failure is not None and failure['category'] == 'rate_limit_quota'
            scope = failure['scope'] if failure else None
            target = '\0connection' if scope in {'connection', 'account'} else self.provider_key(model) if cooldown and scope == 'provider' else model
            key = self.key(endpoint, target, connection_revision)
            record = self.records.setdefault(key, {})
            record["updated_at"] = time.time()
            if failure: record['failure'] = failure
            if cooldown:
                record.update(retry_at=time.time() + min(86400, max(1, getattr(error,'retry_after',None) or 120)),
                              cooldown_scope=scope, retry_known=getattr(error,'retry_after',None) is not None, last_error=failure['action'])
            elif error is not None:
                record.pop("cooldown_scope", None)
                record.pop("retry_known", None)
                field = 'failures' if failure['quality_impact'] else 'availability_failures'
                failures = record.get(field, 0) + 1
                record[field] = failures
                delay = 0 if failure['category'] == 'malformed_request' else min(3600, 900 * 2 ** min(failures - 1, 2))
                record.update(retry_at=time.time() + delay, last_error=failure['action'], retry_known=False)
                if scope in {'connection', 'account'}: record['cooldown_scope'] = scope
            else:
                record.update(retry_at=0, last_error="")
                record.pop('failure', None)
                record.pop("cooldown_scope", None)
                record.pop("retry_known", None)
                if probe:
                    record['probe_contract_version'] = route_health.PROBE_VERSION
                    record['probe_identity'] = probe_identity
                    record['tool_check_source'] = 'validated_tool_response'
                    record["tool_check_passed"] = True
                    record['tool_check_at'] = time.time()
                    if connection_revision is not None: record['tool_connection_revision'] = connection_revision
                else:
                    record["failures"] = 0
                    record['request_observed_at'] = time.time()
                    record['request_source'] = 'actual_request'
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

    def fresh_probe(self, endpoint, model, connection_revision, identity, now=None):
        health = self.observation(endpoint, model, connection_revision)
        age = (time.time() if now is None else now) - health.get('tool_check_at', 0)
        return bool(not health['cooling_down'] and not health.get('last_error')
                    and health.get('tool_check_passed') and 0 <= age < 300
                    and health.get('probe_contract_version') == route_health.PROBE_VERSION
                    and health.get('probe_identity') == identity)

    def claim_probe(self, identity):
        with self.lock:
            if identity in self.inflight_probes: return False, self.inflight_probes[identity]
            if len(self.inflight_probes) >= 4: return False, None
            event = threading.Event()
            self.inflight_probes[identity] = event
            return True, event

    def release_probe(self, identity, event):
        with self.lock:
            if self.inflight_probes.get(identity) is event:
                del self.inflight_probes[identity]
                event.set()

    def rank(self, endpoint, model, role, preferred=None, connection_revision=None):
        health = self.observation(endpoint, model["id"], connection_revision)
        evidence=health['role_evidence'].get(role,{})
        enough=evidence.get('samples',0)>=3
        successes=evidence.get('checkpoints',0) if role=='worker' else evidence.get('reviews_completed',0)
        invalid=evidence.get('invalid_output',0)
        tier=1 if enough and invalid>=3 and invalid>successes else -1 if enough and successes>=3 and invalid==0 else 0
        if connection_revision is not None and tier < 0: tier = 0
        # Observed compatibility first. Metadata only breaks ties; it is not a quality rating.
        return (model["id"] != preferred if preferred else False, -min(evidence.get("independently_validated",0),3), -min(evidence.get("completed",0),3), min(evidence.get("independently_disproved",0),3), tier, -min(evidence.get('accepted',0),3) if enough else 0, -min(health.get(role + "_responses", 0), 1) if connection_revision is None else 0,
                -self.fresh_probe(endpoint, model["id"], connection_revision, route_health.probe_identity(endpoint,model,connection_revision)),
                -(model.get("reasoning") is True) if role == "reviewer" else 0,
                -min(model.get("context_length") or 0, 65536) if role == "reviewer" else 0,
                health.get(role + "_seconds", float("inf")) if connection_revision is None else float("inf"), model["id"])

    def record_outcome(self, endpoint, model, role, run_id, task_id, signals, connection_revision=None):
        """One bounded, idempotent observation per role/model/run; no raw output."""
        if role not in {'worker','reviewer'}:return
        with self.lock:
            record=self.records.setdefault(self.key(endpoint,model,connection_revision),{})
            history=record.setdefault('outcomes',[])
            identity=hashlib.sha256((run_id+'\n'+role).encode()).hexdigest()
            previous=next((h for h in history if h.get('id')==identity),{})
            item={'id':identity,'task':hashlib.sha256(task_id.encode()).hexdigest(),'role':role,'time':previous.get('time',time.time()),'connection_revision':connection_revision,
                  **{k:max(0,int(signals.get(k,0))) for k in ('valid_calls','edits','checks_passed','checkpoints','reviews_completed','invalid_output','accepted')}}
            item['accepted']=max(item['accepted'],previous.get('accepted',0))
            history[:]=[h for h in history if h.get('id')!=identity and h.get('time',0)>=time.time()-30*86400]+[item]
            record['outcomes']=history[-64:];record['updated_at']=time.time();record['outcome_schema']=1
            if len(self.records)>2000:self.records=dict(sorted(self.records.items(),key=lambda item:item[1].get('updated_at',0))[-2000:])
            write_json(self.path,self.records);self.revision+=1

    def record_acceptance(self, endpoint, model, role, task_id, run_id, connection_revision=None):
        identity=hashlib.sha256((run_id+'\n'+role).encode()).hexdigest()
        task_key=hashlib.sha256(task_id.encode()).hexdigest()
        with self.lock:
            record=self.records.get(self.key(endpoint,model,connection_revision),{})
            for item in record.get('outcomes',[]):
                if item['id']==identity and item['task']==task_key:
                    item['accepted']=1
                    write_json(self.path,self.records);self.revision+=1
                    break

    def record_completion(self, scope, role, task_id, run_id, item_id, receipt_id, candidate_id):
        """Controller-only validated receipt projection; no text, endpoint or secrets persisted."""
        if role not in {'worker','reviewer'} or scope.get('role') != role:
            raise ValueError('Completion role mismatch')
        if not all(isinstance(scope.get(k),str) and scope[k] for k in ('base_url','model','connection_revision')):
            raise ValueError('Missing dispatch scope')
        identity=hashlib.sha256((task_id+'\n'+run_id+'\n'+item_id+'\n'+receipt_id+'\n'+role).encode()).hexdigest()
        with self.lock:
            record=self.records.setdefault(self.key(scope['base_url'],scope['model'],scope['connection_revision']),{})
            history=record.setdefault('completions',[])
            if any(c['id']==identity for c in history):return
            history.append({'id':identity,'role':role,'receipt_id':receipt_id,'candidate_id':candidate_id,
                            'task':hashlib.sha256(task_id.encode()).hexdigest(),'run':run_id,'item':item_id,
                            'connection_revision':scope['connection_revision'],'time':time.time(),
                            'verdict':'unvalidated','human_integrated':False})
            record['completions']=history[-128:];record['updated_at']=time.time()
            if len(self.records)>2000:self.records=dict(sorted(self.records.items(),key=lambda item:item[1].get('updated_at',0))[-2000:])
            write_json(self.path,self.records);self.revision+=1

    def adjudicate_completion(self, endpoint, model, role, receipt_id, evidence_digest, passed, connection_revision):
        """Trusted local observer API ONLY. No tool/HTTP route accepts worker claims here.

        Caller independently checks the exact receipt/candidate and supplies its
        retained artifact SHA256. Disproof is sticky; a new candidate gets a new
        receipt. This records observer evidence, not a calculated accuracy score.
        """
        import re
        if type(passed) is not bool or not re.fullmatch('[a-f0-9]{64}',evidence_digest):
            raise ValueError('Require boolean verdict and independent artifact SHA256')
        with self.lock:
            matches=[c for c in self.records.get(self.key(endpoint,model,connection_revision),{}).get('completions',[])
                     if c['role']==role and c['receipt_id']==receipt_id and c['connection_revision']==connection_revision]
            if len(matches)!=1:raise ValueError('No unique matching observed completion')
            item=matches[0]
            observations=item.setdefault('independent_evidence',[])
            event={'digest':evidence_digest,'passed':passed}
            if event in observations:return
            if any(e['digest']==evidence_digest for e in observations):raise ValueError('Artifact verdict conflicts')
            observations.append(event);item['independent_evidence']=observations[-16:]
            item['verdict']='disproved' if not passed or item['verdict']=='disproved' else 'validated'
            write_json(self.path,self.records);self.revision+=1

    def mark_integrated(self, task_id, run_id):
        """Called only after completed matching controller merge receipt."""
        task_hash=hashlib.sha256(task_id.encode()).hexdigest()
        with self.lock:
            changed=False
            for record in self.records.values():
                for item in record.get('completions',[]):
                    if item['task']==task_hash and item['run']==run_id and not item['human_integrated']:
                        item['human_integrated']=True;changed=True
            if changed:write_json(self.path,self.records);self.revision+=1


def observe_completions(pool, task):
    """Reconstruct immutable receipt validity without rechecking a later workspace.

    Commit controller already validated current files/checks before CAS. We
    recheck saved candidate-bound required checks and matching operation identity.
    Sparse historical dispatch provenance is unknown and never guessed.
    """
    from . import branch_evidence as evidence
    run=task.get('branch_run') or {}
    if task.get('demo'):return
    for item in run.get('items',[]):
        op=item.get('commit_receipt') or {}
        if item.get('status') not in {'committed','satisfied_without_change'} or op.get('stage')!='completed' or op.get('run_id')!=run.get('id') or op.get('item_id')!=item.get('id'):continue
        try:
            saved=json.loads(op['receipt']);candidate=saved['candidate'];context=candidate['context']
            if evidence._digest({k:v for k,v in candidate.items() if k!='id'})!=candidate['id']:continue
            if context['run_id']!=run['id'] or context['item_id']!=item['id'] or op['candidate_id']!=candidate['id']:continue
            if candidate['criteria']!=item['acceptance_criteria'] or [c['command'] for c in candidate['checks']]!=evidence.commands(item['required_checks']):continue
            rebuilt=evidence.ready_receipt(candidate,saved['checks'],saved['review'],saved['worker_model'],saved['reviewer_model'],saved['criteria_outcomes'])
            if rebuilt!=op['receipt'] or op['outcome']!=saved['outcome']:continue
            if (item['status']=='satisfied_without_change') != (saved['outcome']=='satisfied_without_change'):continue
            import re
            if not isinstance(op.get('new_tip'),str) or not re.fullmatch('(?:[a-f0-9]{40}|[a-f0-9]{64})',op['new_tip']):continue
            if not isinstance(op.get('old_tip'),str) or not re.fullmatch('(?:[a-f0-9]{40}|[a-f0-9]{64})',op['old_tip']) or op['old_tip']!=context.get('feature_parent'):continue
            if item['status']=='committed' and op.get('old_tip')==op['new_tip']:continue
            if item['status']=='satisfied_without_change' and op.get('old_tip')!=op['new_tip']:continue
            for role in ('worker','reviewer'):
                model=saved[role+'_model']
                scopes={json.dumps(q['dispatch_scope'],sort_keys=True) for q in task.get('request_metrics',[]) if q.get('dispatched') and q.get('purpose')!='probe'
                        and q.get('branch_item_id')==item['id'] and q.get('role')==role and q.get('dispatch_scope')
                        and evidence.model_identity(q['model'])==model}
                if len(scopes)!=1:continue
                scope=json.loads(scopes.pop())
                if scope.get('role')!=role or evidence.model_identity(scope.get('model'))!=model:continue
                pool.record_completion(scope,role,task['id'],run['id'],item['id'],saved['id'],candidate['id'])
        except (KeyError,TypeError,ValueError):
            continue
