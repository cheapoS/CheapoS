"""Typed, bounded pause explanations. Records describe actions, never grant them."""
import math
import re

TEMPLATES = {
 'operator': ('You paused this run.', 'resume'),
 'restart': ('Execution was interrupted by a restart.', 'resume'),
 'missing_setup': ('The task verification environment needs setup.', 'environment'),
 'command_grant': ('A verification command needs your permission.', 'permission'),
 'exhausted_work': ('The authorized work allowance is exhausted.', 'limits'),
 'branch_drift': ('The branch changed since the saved operation.', 'inspect'),
 'authority_changed': ('The saved authorization no longer matches this run.', 'authorization'),
 'provider_quota': ('The provider reported a rate limit or exhausted quota.', 'models'),
 'provider_connection': ('The configured provider connection could not complete the request.', 'models'),
 'malformed_output': ('The model returned an invalid response or tool arguments.', 'correction'),
 'repeated_work': ('Repeated work stopped making progress.', 'correction'),
 'essential_clarification': ('An essential decision is needed before work can continue.', 'reply'),
 'repeated_review_dispute': ('Review disagreement needs a decision before more repair work.', 'review_dispute'),
 'unknown': ('This run stopped for an unclassified reason. Inspect the retained diagnostic.', 'inspect'),
}
CODES = {'gateway_cooldown':'provider_quota','http_429':'provider_quota',
 'endpoint_unavailable':'provider_connection','http_401':'provider_connection','http_403':'provider_connection','http_402':'provider_connection',
 'invalid_tool_arguments':'malformed_output','invalid_tool_envelope':'malformed_output','invalid_response_json':'malformed_output','invalid_stream_json':'malformed_output','stream_error':'malformed_output',
 'progress_limit':'repeated_work','worker_recovery_exhausted':'repeated_work','recovery_exhausted':'repeated_work',
 'http_500':'provider_connection','http_502':'provider_connection','http_503':'provider_connection','http_504':'provider_connection','request_timeout':'provider_connection','routing_unavailable':'provider_connection',
 'worker_turn_limit':'exhausted_work','iteration_limit':'exhausted_work','reviewer_token_limit':'exhausted_work','budget_exceeded':'exhausted_work',
 'environment_missing':'missing_setup','missing_executable':'missing_setup','command_permission_required':'command_grant',
 'authority_changed':'authority_changed','branch_drift':'branch_drift','review_dispute':'repeated_review_dispute','essential_clarification':'essential_clarification'}
STAGES={'planning','working','checking','reviewing','committing','finalizing','merging','unknown'}

class PauseError(ValueError):
    def __init__(self, cause, stage=None, diagnostic_id=None):
        self.pause_cause=cause if cause in TEMPLATES else 'unknown'
        self.stage=stage;self.diagnostic_id=diagnostic_id
        super().__init__(TEMPLATES[self.pause_cause][0])

def label(value):
    return value if isinstance(value,str) and len(value)<=120 and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]*',value) and '://' not in value and not value.startswith('/') else None

def public(value):
    if not isinstance(value,dict) or type(value.get('version')) is not int or value.get('version')!=1:return None
    cause=value.get('cause') if value.get('cause') in TEMPLATES else 'unknown'
    explanation,action=TEMPLATES[cause]
    result={'version':1,'cause':cause,'explanation':explanation,'next_action':action,'stage':value.get('stage') if value.get('stage') in STAGES else 'unknown'}
    for key in ('item_id','model','diagnostic_id'):
        if label(value.get(key)):result[key]=label(value[key])
    if value.get('role') in ('worker','reviewer','coordinator'):result['role']=value['role']
    if cause=='provider_quota':
        if value.get('cooldown_scope') in ('model','provider','account','connection'):result['cooldown_scope']=value['cooldown_scope']
        at=value.get('retry_at')
        if type(at) in (float,int) and math.isfinite(at) and at>0:result['retry_at']=at
    return result

def classify(error=None, task=None, cause=None, stage=None):
    task=task or {};run=task.get('branch_run') or {}
    from .branch_budget import LimitExceeded
    explicit=cause or getattr(error,'pause_cause',None)
    code=getattr(error,'code',None) or task.get('error_code')
    if not explicit:
        if isinstance(error,LimitExceeded):explicit='exhausted_work'
        elif isinstance(error,InterruptedError):explicit='operator'
        elif task.get('pending_approval'):explicit='command_grant'
        elif task.get('environment_setup',{}).get('status')=='missing':explicit='missing_setup'
        else:explicit=CODES.get(code,'unknown')
    if explicit=='unknown' and run.get('pause_detail') and run.get('status') in ('paused','blocked'):
        return public(run['pause_detail']) or public({'version':1,'cause':'unknown'})
    item=next((i for i in run.get('items',[]) if i.get('id')==run.get('current_item_id')), {})
    requests=task.get('request_metrics') or [];request=requests[-1] if requests else {}
    detail={'version':1,'cause':explicit,'stage':stage or getattr(error,'stage',None) or (run.get('status') if run.get('status') in STAGES else 'reviewing' if task.get('active_role')=='reviewer' else item.get('status')),
            'item_id':item.get('id'),'role':request.get('role') or task.get('active_role'),'model':request.get('model'),
            'diagnostic_id':getattr(error,'diagnostic_id',None) or request.get('id')}
    detail['cooldown_scope']=getattr(error,'scope',None)
    detail['retry_at']=getattr(error,'retry_at',None) or (task.get('route_unavailable') or {}).get('retry_at')
    return public(detail)

def clear(run):run.pop('pause_detail',None)

def apply(task,error=None,cause=None,stage=None):
    from . import branch_runs
    detail=classify(error,task,cause,stage);run=task['branch_run']
    reason={'provider_quota':'missing_information','provider_connection':'missing_information','malformed_output':'recovery_exhausted','repeated_work':'recovery_exhausted','essential_clarification':'missing_information','repeated_review_dispute':'recovery_exhausted','unknown':'missing_information'}.get(detail['cause'],detail['cause'])
    run.update(status='paused',pause_reason=reason,pause_detail=detail)
    task.update(status='paused',error=detail['explanation'],stream=None,check_stream=None)
    branch_runs.append_event(run,'paused',{'reason':reason,'pause_detail':detail})
    return detail
