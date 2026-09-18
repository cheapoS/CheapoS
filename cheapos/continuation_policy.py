"""One next-action decision per failure episode; existing executors own dispatch.

This module does not grant access, reserve/refund usage, or execute any action.
"""
import re
from .progress import digest
from .provider_recovery import OUTAGES


def is_continue(message):
    if not isinstance(message, str):
        return False
    text = message.strip().casefold()
    if not text:
        return False
    if re.search(r'\b(?:do\s+not|don\'?t|cannot|can\'?t|won\'?t|never|not|disapprove|deny|reject)\b', text):
        return False
    if re.search(r'\bapprov', text):
        return True
    normalized = re.sub(r'[\s.,!?]+', ' ', text).strip()
    if normalized in {
        'continue', 'continue please', 'please continue', 'try again', 'resume', 'do what you need to finish',
        'start', 'start run', 'start plan', 'start task', 'proceed', 'looks good', 'looks good continue',
        'go ahead', 'yes continue', 'ok continue', 'looks good go ahead', 'good to go', 'lgtm',
        'sounds good', 'looks great', 'go for it', 'let\'s go', 'lets go', 'do it', 'lets do it', 'let\'s do it',
        'sure', 'yes', 'ok', 'okay', 'yep', 'yeah', 'yup', 'fine'
    }:
        return True
    return bool(
        re.fullmatch(r'(?:(?:yes|yeah|yep|sure)[,\s]+)?(?:(?:i\s+think\s+)?(?:this\s+)?(?:looks|sounds)\s+(?:good|great|fine)|ok|okay|good\s+to\s+go|lgtm)[,\s]*(?:to\s+me)?[,\s]*(?:continue|start|proceed|go\s+ahead|go\s+for\s+it)?', normalized) or
        re.fullmatch(r'(?:(?:yes|yeah|yep|sure|please)[,\s]+)?(?:continue|proceed|resume|start)[,\s]*(?:please|(?:with\s+)?(?:the\s+)?(?:plan|task|run|work))?', normalized) or
        re.fullmatch(r'(?:(?:yes|yeah|yep|sure)[,\s]+)?(?:go\s+ahead|go\s+for\s+it)[,\s]*(?:and\s+(?:start|run|proceed))?', normalized)
    )



def is_implementation(task):
    from . import work_policy
    from .engine import needs_patch_review
    prompt = (task.get('requests') or [task.get('prompt', '')])[-1]
    if isinstance(prompt, str):
        prompt_clean = prompt.strip().casefold()
        if re.search(r'\b(?:do\s+not\s+edit|without\s+(?:making\s+)?(?:more\s+)?changes|no\s+changes|don\'?t\s+change|don\'?t\s+edit)\b', prompt_clean):
            return False
        if re.search(r'^(?:how\s+(?:do|can|to|would|should)|what\s+(?:is|are|does|did)|why\s+(?:is|does|do|did)|where\s+(?:is|are|does|can)|explain\b|describe\b|tell\s+me\b|can\s+you\s+(?:find|tell|explain|show)\b)', prompt_clean):
            return False
        action_keywords = {'fix', 'update', 'change', 'add', 'implement', 'create', 'delete', 'remove',
                           'replace', 'make', 'edit', 'patch', 'build', 'refactor', 'repair', 'resolve',
                           'write', 'modify', 'adjust', 'correct', 'clean', 'hide', 'disable', 'enable'}
        if any(re.search(r'\b' + re.escape(w) + r'\b', prompt_clean) for w in action_keywords):
            return True
        # Behavioral requests often describe the desired UI without saying
        # "edit" or "fix". A conditional display rule still asks for work.
        if re.search(r'\bonly\s+show\b[^.!?]*\b(?:if|when)\b', prompt_clean):
            return True
    if work_policy.active_implementation(task) or needs_patch_review(task):
        return True
    return False


def decide(task, trigger=None):
    if trigger=='repeated_evidence':
        implementation = is_implementation(task)
        return {'kind':'implementation' if implementation else 'investigation',
                'action':'act' if implementation else 'answer',
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
    if code=='controller_error':
        return {'kind':'controller','action':'repair_controller','reason':'The request failed inside cheapoS; retain evidence and do not replace healthy models.'}
    if trigger=='final_review_stall':
        from .model_pool import automatic
        config=task.get('providers',{}).get('reviewer') or {}
        reviewer=config.get('model') if isinstance(config,dict) else config
        can_switch=automatic(task,'reviewer') and task.get('operator_reviewer_model')!=reviewer
        return {'kind':'review','action':'recover_review' if can_switch else 'choose_reviewer',
                'reason':'Continue final review with an unused authorized reviewer.' if can_switch else
                         'The selected reviewer could not finish; choose another reviewer for this saved task.'}
    if task.get('pending_review') or task.get('status')=='reviewing':
        stalled = (task.get('pending_review') or {}).get('stop_diagnostic') or {}
        if run and stalled.get('kind') == 'review_stall':
            from .model_pool import automatic
            reviewer = (task.get('providers', {}).get('reviewer') or {}).get('model')
            can_switch = automatic(task, 'reviewer') and task.get('operator_reviewer_model') != reviewer
            return {'kind':'review','action':'recover_review' if can_switch else 'choose_reviewer',
                    'reason':'Continue saved review with an unused authorized reviewer.' if can_switch else
                             'The selected reviewer stalled; approve a replacement for this task.'}
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
    return (not stopped and task.get('status') in {'paused', 'error'}
            and task.get('error_code') not in {'environment_setup', 'worker_turn_limit', 'working_time_limit', 'controller_error'}
            and not task.get('limit_hit') and task.get('status') != 'budget_paused'
            and item.get('status')=='working' and task.get('active_role')=='worker'
            and decide(task)['action'] in {'continue_worker','repair','expand_tests','route_recovery'})


def strategy_episode(task, role, failure, identity, strategies):
    """Select an unused technique for this exact failure, without renewing usage."""
    key = digest([role, identity, failure])
    episodes = task.setdefault('strategy_episodes', {})
    episode = episodes.setdefault(key, {'role': role, 'identity': identity,
                                        'failure': failure, 'attempts': [], 'observations': 0})
    episode['observations'] += 1
    attempted = {a['strategy'] for a in episode['attempts']}
    selected = next((s for s in strategies if s not in attempted), None)
    if selected:
        episode['attempts'].append({'strategy': selected, 'status': 'selected'})
    episode['next_action'] = selected or 'prerequisite'
    task['strategy_continuation'] = {'episode': key, 'action': episode['next_action']}
    return episode


def dispatched_strategy(task, record):
    """Link the selected strategy to the existing durable request outcome."""
    selected = task.get('strategy_continuation') or {}
    episode = task.get('strategy_episodes', {}).get(selected.get('episode'))
    if not episode or episode['role'] != record['role']: return
    attempt = next((a for a in episode['attempts'] if a['status'] == 'selected'), None)
    if attempt:
        attempt.update(status='dispatched', request_id=record['id'])
        record['strategy_episode'] = selected['episode']
