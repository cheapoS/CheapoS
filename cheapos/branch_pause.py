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
 'review_context_unavailable': ('Final review needs candidate context that could not be obtained. Inspect the saved context-read diagnostic before retrying.', 'inspect'),
 'failed_checks': ('Verification checks failed. Inspect the recorded test results before changing or retrying the work.', 'inspect'),
 'review_identity_unknown': ('Reviewer independence could not be established. Open Choose reviewer to see available routes and any missing historical identity.', 'reviewer'),
 'review_identity_conflict': ('The worker and reviewer resolved to the same model. Choose a different reviewer; saved work and passing checks are kept.', 'reviewer'),
 'controller_error': ('cheapoS encountered an internal execution error. Saved edits and usage are retained. This needs an app fix; changing your task instructions will not repair the error.', 'inspect'),
 'unknown': ('No safe specific diagnostic was recorded for this stop. Inspect the saved task details before continuing.', 'inspect'),
 'reviewer_recovery_required': ('Automatic reviewer recovery could not finish. Choose reviewer to select an eligible model; saved work and passing checks are kept.', 'reviewer'),
}
CODES = {'reviewer_recovery_required':'reviewer_recovery_required','review_identity_unknown':'review_identity_unknown','review_identity_conflict':'review_identity_conflict','controller_error':'controller_error','gateway_cooldown':'provider_quota','http_429':'provider_quota',
 'endpoint_unavailable':'provider_connection','http_401':'provider_connection','http_403':'provider_connection','http_402':'provider_connection',
 'invalid_tool_arguments':'malformed_output','invalid_tool_envelope':'malformed_output','invalid_response_json':'malformed_output','invalid_stream_json':'malformed_output','stream_error':'malformed_output',
 'progress_limit':'repeated_work','worker_recovery_exhausted':'repeated_work','recovery_exhausted':'repeated_work',
 'http_500':'provider_connection','http_502':'provider_connection','http_503':'provider_connection','http_504':'provider_connection','request_timeout':'provider_connection','routing_unavailable':'provider_connection',
 'transport_retry_exhausted':'provider_connection','streaming_unsupported':'provider_connection',
 'worker_turn_limit':'exhausted_work','iteration_limit':'exhausted_work','reviewer_token_limit':'exhausted_work','budget_exceeded':'exhausted_work',
 'environment_missing':'missing_setup','missing_executable':'missing_setup','command_permission_required':'command_grant',
 'authority_changed':'authority_changed','branch_drift':'branch_drift','review_dispute':'repeated_review_dispute','essential_clarification':'essential_clarification'}
STAGES={'planning','working','checking','reviewing','committing','finalizing','merging','unknown'}
TRANSPORT_ERRORS = {
 'transport_retry_exhausted': 'The streamed model reply failed again after its transport retry was used. Saved edits and guidance are intact. Retry continues from them using proven transport compatibility or an eligible model within the saved routing policy.',
 'streaming_unsupported': 'The model connection did not support streaming. Saved work is intact. Retry continues within the saved routing policy.',
}

class PauseError(ValueError):
    def __init__(self, cause, stage=None, diagnostic_id=None, *, diagnostic=None):
        self.pause_cause=cause if cause in TEMPLATES else 'unknown'
        self.stage=stage;self.diagnostic_id=diagnostic_id
        self.safe_diagnostic=diagnostic
        super().__init__(specific(diagnostic) or TEMPLATES[self.pause_cause][0])

def label(value):
    return value if isinstance(value,str) and len(value)<=120 and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]*',value) and '://' not in value and not value.startswith('/') else None

def safe_text(value):
    """Only bounded app-authored diagnostics, never a raw provider exception."""
    if not isinstance(value,str) or not value.strip() or len(value)>400:return None
    if re.search(r'[<>\x00-\x1f]|https?://|(?i:authorization|bearer|api[_ -]?key|password|secret|token)\s*[:=]|(?i:sk-|eyJ)[A-Za-z0-9_-]{8,}',value):return None
    return value.strip()

def specific(diagnostic):
    if not isinstance(diagnostic,dict):return None
    kind=diagnostic.get('kind')
    if kind=='transport' and isinstance(diagnostic.get('code'),str):
        return TRANSPORT_ERRORS.get(diagnostic['code'])
    if kind=='worker_stall':
        count=diagnostic.get('saved_files')
        if type(count) is not int or not 0<=count<=100000 or type(diagnostic.get('assisted')) is not bool:return None
        reason=safe_text(diagnostic.get('reason'))
        if not reason:return None
        return ('Worker could not choose the next step after recovery. ' + reason +
                (' A local coordinator consultation was attempted.' if diagnostic['assisted'] else '') +
                ' %s changed file(s) are saved. Inspect the work or continue in Chat; Resume does not renew recovery attempts.' % count)
    if kind=='review_stall':
        if not isinstance(diagnostic.get('reason'),str) or type(diagnostic.get('coached')) is not bool:return None
        reasons={
            'repeated_evidence':'The reviewer repeated the same unchanged evidence three times without a decision.',
            'repeated_tool_error':'The reviewer repeated the same failed tool action three times without resolving its error.',
            'missing_decision':'The reviewer returned no usable review action three times.',
            'invalid_decision':'Unsupported review responses failed validation three times.',
            'request_limit':'The reviewer reached the item-review request limit without a valid decision.'}
        reason=reasons.get(diagnostic.get('reason'))
        if reason is None:return None
        recovery=' cheapoS already requested a focused reassessment using saved findings and check evidence.' if diagnostic['coached'] else ''
        return reason+recovery+' Review remains unfinished. Inspect the review attempts or choose another reviewer.'
    if kind=='missing_executable':
        runner=diagnostic.get('executable')
        # Display just a conventional executable basename, never a private path.
        if not isinstance(runner,str):return None
        runner=runner.replace('\\','/').rsplit('/',1)[-1]
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,120}',runner):return None
        return "Verification could not run because the selected executable '%s' is unavailable. Choose an available executable and re-check this task's environment." % runner
    if kind=='safe_message':return safe_text(diagnostic.get('message'))
    if kind in {'limit', 'request_budget'}:
        key=label(diagnostic.get('key'));used=diagnostic.get('used');allowed=diagnostic.get('allowed')
        if key and all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in (used,allowed)):
            if kind == 'request_budget':
                return 'The next model request does not fit the remaining %s allowance (%s used / %s allowed). Saved work is intact; review work limits before continuing.' % (key,used,allowed)
            return 'The authorized %s allowance was reached (%s used / %s allowed). Inspect work limits before authorizing more work.' % (key,used,allowed)
    return None

def public(value):
    if not isinstance(value,dict) or type(value.get('version')) is not int or value.get('version')!=1:return None
    cause=value.get('cause') if value.get('cause') in TEMPLATES else 'unknown'
    explanation,action=TEMPLATES[cause]
    diagnostic=value.get('diagnostic')
    if specific(diagnostic):explanation=specific(diagnostic)
    if isinstance(diagnostic,dict) and diagnostic.get('kind')=='review_stall' and specific(diagnostic):action='inspect'
    if cause=='provider_connection' and isinstance(diagnostic,dict) and diagnostic.get('kind')=='transport' and specific(diagnostic):action='resume'
    result={'version':1,'cause':cause,'explanation':explanation,'next_action':action,'stage':value.get('stage') if value.get('stage') in STAGES else 'unknown'}
    if specific(diagnostic):result['diagnostic']=({'kind':'review_stall','reason':diagnostic['reason'],'coached':diagnostic['coached']}
        if diagnostic.get('kind')=='review_stall' else {'kind':'transport','code':diagnostic['code']}
        if diagnostic.get('kind')=='transport' else {'kind':'safe_message','message':explanation})
    for key in ('item_id','model','diagnostic_id'):
        if label(value.get(key)):result[key]=label(value[key])
    if value.get('role') in ('worker','reviewer','coordinator','planner'):result['role']=value['role']
    if cause=='provider_quota':
        if value.get('cooldown_scope') in ('model','provider','account','connection'):result['cooldown_scope']=value['cooldown_scope']
        at=value.get('retry_at')
        if type(at) in (float,int) and math.isfinite(at) and at>0:result['retry_at']=at
        if result.get('cooldown_scope'):result['explanation']+=' The reported cooldown applies to the '+result['cooldown_scope']+'.'
    return result

def classify(error=None, task=None, cause=None, stage=None):
    task=task or {};run=task.get('branch_run') or {}
    from .branch_budget import LimitExceeded
    from .providers import BudgetError
    explicit=cause or getattr(error,'pause_cause',None)
    code=getattr(error,'code',None) or task.get('error_code')
    if not explicit:
        if isinstance(error,LimitExceeded):explicit='exhausted_work'
        elif isinstance(error,InterruptedError):explicit='operator'
        elif task.get('pending_approval'):explicit='command_grant'
        elif task.get('environment_setup',{}).get('status')=='missing':explicit='missing_setup'
        else:
            if code == 'routing_unavailable' and ((task.get('route_unavailable') or {}).get('scope') in {'model', 'provider', 'connection', 'account'} or getattr(error, 'scope', None) in {'model', 'provider', 'connection', 'account'} or (task.get('route_unavailable') or {}).get('retry_at') or getattr(error, 'retry_at', None)):
                explicit = 'provider_quota'
            else:
                explicit = CODES.get(code, 'unknown')
    requests = task.get('request_metrics') or []; request = requests[-1] if requests else {}
    previous = run.get('pause_detail') or {}
    if explicit == 'unknown' and not getattr(error, 'safe_diagnostic', None) and previous and run.get('status') in ('paused', 'blocked') and request.get('id') and previous.get('diagnostic_id') == request.get('id'):
        return public(run['pause_detail']) or public({'version': 1, 'cause': 'unknown'})
    item = next((i for i in run.get('items', []) if i.get('id') == run.get('current_item_id')), {})
    requests = task.get('request_metrics') or []; request = requests[-1] if requests else {}
    if explicit == 'repeated_work':
        diagnostic = (getattr(error, 'safe_diagnostic', None) or
                      (task.get('pending_review') or {}).get('stop_diagnostic'))
        review_stop = isinstance(diagnostic, dict) and diagnostic.get('kind') == 'review_stall'
        stalled_role = 'reviewer' if review_stop else task.get('active_role')
        request = next((r for r in reversed(requests) if r.get('role') == stalled_role), request)
    detail = {'version': 1, 'cause': explicit, 'stage': stage or getattr(error, 'stage', None) or (run.get('status') if run.get('status') in STAGES else 'reviewing' if task.get('active_role') == 'reviewer' else item.get('status')),
              'item_id': item.get('id'), 'role': request.get('role') or task.get('active_role'), 'model': request.get('model'),
              'diagnostic_id': getattr(error, 'diagnostic_id', None) or request.get('id')}
    diagnostic = getattr(error, 'safe_diagnostic', None)
    if not diagnostic and explicit == 'provider_connection' and code in TRANSPORT_ERRORS:
        diagnostic = {'kind': 'transport', 'code': code}
    if explicit == 'repeated_work' and not diagnostic:
        diagnostic = (task.get('pending_review') or {}).get('stop_diagnostic')
        if not diagnostic and task.get('active_role') == 'worker':
            from .coordinator_recovery import episode_key
            reason = safe_text((task.get('pause_summary') or {}).get('blocker'))
            if reason:
                diagnostic = {'kind': 'worker_stall', 'reason': reason, 'saved_files': len(task.get('changes', [])),
                              'assisted': any(e.get('key') == episode_key(task) for e in task.get('coordinator_recovery', []))}
    if isinstance(error, LimitExceeded): diagnostic = {'kind': 'limit', 'key': error.key, 'used': error.used, 'allowed': error.allowed}
    if isinstance(error, BudgetError) and error.limit_hit:
        diagnostic = {'kind': 'request_budget', **error.limit_hit}
    if diagnostic: detail['diagnostic'] = diagnostic
    if explicit == 'malformed_output' and not specific(diagnostic):
        role = detail.get('role') or ('planner' if detail.get('stage') == 'planning' else 'model')
        detail['diagnostic'] = {'kind': 'safe_message', 'message': 'The %s returned an invalid response. %s remains unfinished; inspect the response failure and add a correction before retrying.' % (role, 'Review' if role == 'reviewer' else 'Planning' if role == 'planner' else 'Work')}
    detail['cooldown_scope'] = getattr(error, 'scope', None) or (task.get('route_unavailable') or {}).get('scope')
    detail['retry_at'] = getattr(error, 'retry_at', None) or (task.get('route_unavailable') or {}).get('retry_at')
    return public(detail)

def for_task(task):
    """Reclassify an old unknown transport stop from its same retained request.

    Do not relabel a newer operator/permission/limit stop using an older error.
    This read-only projection preserves the original record for diagnostics.
    """
    run = task.get('branch_run') or {}
    if run.get('status') not in {'paused', 'blocked'}: return None
    detail = public(run.get('pause_detail'))
    request = (task.get('request_metrics') or [{}])[-1]
    if (detail and detail['cause'] in {'unknown', 'provider_connection'}
            and not detail.get('diagnostic')
            and (task.get('error_code') in TRANSPORT_ERRORS or task.get('error_code') in {'review_identity_unknown','review_identity_conflict','reviewer_recovery_required'} or (task.get('route_unavailable') or {}).get('scope') in {'model', 'provider'})
            and request.get('id') and detail.get('diagnostic_id') == request['id']):
        return classify(task=task, stage=detail.get('stage'))
    return detail

def clear(run):run.pop('pause_detail',None)

def apply(task,error=None,cause=None,stage=None):
    from . import branch_runs
    detail=classify(error,task,cause,stage);run=task['branch_run']
    reason={'review_identity_unknown':'missing_information','review_identity_conflict':'missing_information','provider_quota':'missing_information','provider_connection':'missing_information','malformed_output':'recovery_exhausted','repeated_work':'recovery_exhausted','essential_clarification':'missing_information','repeated_review_dispute':'recovery_exhausted','unknown':'missing_information'}.get(detail['cause'],detail['cause'])
    run.update(status='paused',pause_reason=reason,pause_detail=detail)
    task.update(status='paused',error=detail['explanation'],stream=None,check_stream=None)
    branch_runs.append_event(run,'paused',{'reason':reason,'pause_detail':detail})
    return detail
