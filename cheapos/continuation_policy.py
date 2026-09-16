"""One next-action decision per failure episode; existing executors own dispatch.

This module does not grant access, reserve/refund usage, or execute any action.
"""
import re
from .progress import digest
from .provider_recovery import OUTAGES


def is_continue(message):
    if not isinstance(message, str):
        return False
    normalized = re.sub(r'[\s.,!?]+', ' ', message.strip().casefold()).strip()
    if normalized in {
        'continue', 'continue please', 'please continue', 'try again', 'resume', 'do what you need to finish',
        'plan approved continue', 'plan approved', 'approved', 'approve',
        'start', 'start run', 'start plan', 'start task', 'proceed', 'looks good', 'looks good continue',
        'go ahead', 'yes continue', 'ok continue', 'looks good go ahead'
    }:
        return True
    return bool(re.fullmatch(r'(?:plan\s+)?approved[,\s]*(?:continue|start|proceed|go ahead)?', normalized) or
                re.fullmatch(r'(?:looks\s+good|ok|okay)[,\s]*(?:continue|start|proceed|go ahead)?', normalized))



def decide(task, trigger=None):
    if trigger=='repeated_evidence':
        from . import work_policy
        from .development import enabled
        from .engine import needs_patch_review
        implementation=(work_policy.active_implementation(task) or needs_patch_review(task)) and not work_policy.read_only(task)
        return {'kind':'implementation' if implementation else 'investigation',
                'action':'continue_worker' if enabled(task) else 'act' if implementation else 'answer',
                'reason':'Use the saved findings to take the next unfinished action; do not repeat unchanged inspection.'}
    code=task.get('error_code')
    run=task.get('branch_run') or {}
    if task.get('pending_approval'):
        return {'kind':'authorization','action':'approve_command','reason':'Approve or deny the displayed command before continuing.'}
    if task.get('environment_setup',{}).get('status')=='missing':
        return {'kind':'environment','action':'repair_environment','reason':'Complete the displayed environment setup, then re-check it.'}
    if run.get('waiting_for_user'):
        return {'kind':'authorization','action':'answer_question','reason':run['waiting_for_user']}
    if task.get('limit_hit') or task.get('status')=='budget_paused':
        return {'kind':'allowance','action':'review_limits','reason':'Review the exhausted allowance; Continue does not replenish usage.'}
    if task.get('pending_review') or task.get('status')=='reviewing':
        return {'kind':'review','action':'continue_review','reason':'Continue the independent review against its saved candidate.'}
    if code in OUTAGES or code=='routing_unavailable':
        return {'kind':'transport','action':'route_recovery','reason':'Continue through existing authorized route recovery; keep completed tool results.'}
    review=(task.get('checkpoints') or [{}])[-1]
    from .working_state import project
    working=project(task)
    if review.get('decision') in {'REQUEST_CHANGES', 'REQUEST_TESTS'}:
        return {'kind':'review','action':'repair' if review.get('decision') == 'REQUEST_CHANGES' else 'expand_tests','reason':working.get('next_action') or ('Expand test coverage for the reviewer-specified edge cases.' if review.get('decision') == 'REQUEST_TESTS' else 'Resolve the recorded review findings in the current worker session.')}
    return {'kind':'implementation','action':'continue_worker','reason':working.get('next_action') or 'Continue from the saved findings; choose the smallest unfinished action.'}


def record(task, trigger):
    value=decide(task, trigger)
    key=digest([task.get('workspace_generation',0),task.get('patch'),task.get('error_code'),
                task.get('branch_run',{}).get('current_item_id'),task.get('requests'),value])
    episodes=task.setdefault('continuation_episodes',[])
    if not episodes or episodes[-1]['key']!=key:
        episodes.append({'key':key,'trigger':trigger,**value,'result':'selected'})
    return value


def implementation_handoff(task, item, stopped=False):
    """Only stalled implementation reaches the branch's existing route executor."""
    return (not stopped and task.get('status')=='paused' and task.get('error_code')=='progress_limit'
            and item.get('status')=='working' and task.get('active_role')=='worker'
            and decide(task)['action'] in {'continue_worker','repair','expand_tests'})