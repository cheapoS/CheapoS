"""Request-scoped durable progress and recovery evidence, without model claims."""
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def state(task):
    segment = len(task.get('requests', [task.get('prompt', '')]))
    value = task.get('progress_state')
    if not value or value.get('segment') != segment:
        value = {'segment': segment, 'revision': 0, 'seen': [digest(item) for item in candidates(task)],
                 'handoffs': 0, 'malformed_attempts': 0, 'answer_attempts': 0}
        task['progress_state'] = value
    return value


def candidates(task):
    candidates = [['patch', task.get('workspace_generation', 0), task.get('patch', '')]]
    if task.get('checks'):
        check = task['checks'][-1]
        candidates.append(['check', check.get('generation', 0), check.get('digest'), check.get('command'), check.get('outcome'), check.get('passed'), check.get('output')])
    if task.get('checkpoints'):
        review = task['checkpoints'][-1]
        # Distinct verified review decisions advance work; wording alone does not.
        candidates.append(['review', review.get('verification_identity'), review.get('decision')])
    if task.get('status') == 'awaiting_reply':
        candidates.append(['answered', len(task.get('requests', [task.get('prompt', '')]))])
    return candidates


def observe(task):
    """New patch/check/review-step evidence only; repeated or toggled states lose."""
    value = state(task)
    advanced = False
    for candidate in candidates(task):
        key = digest(candidate)
        if key not in value['seen']:
            # Bounded task histories; don't evict old states and admit cycles.
            if len(value['seen']) >= 1000:
                continue
            value['seen'].append(key)
            value['revision'] += 1
            advanced = True
    return advanced


def pause_summary(task, blocker):
    value = state(task)
    check = (task.get('checks') or [{}])[-1]
    attempts = []
    if task.get('answer_pending') or value['answer_attempts']:
        attempts.append('answer from gathered evidence')
    if task.get('action_pending') or task.get('compact_edits'):
        attempts.append('small edits from current files')
    if task.get('output_recovery'):
        attempts.append('smaller response')
    if value['handoffs']:
        attempts.append(f"{value['handoffs']} free-model handoff(s)")
    if value['malformed_attempts']:
        attempts.append(f"{value['malformed_attempts']} malformed-call correction(s)")
    return {'blocker': str(blocker), 'attempted': attempts,
            'saved_files': [f['path'] for f in task.get('changes', [])],
            'check': {'command': check.get('command', []), 'passed': check.get('passed'), 'outcome': check.get('outcome')},
            'next_action': 'Add a specific correction or missing information in Chat. Resume alone does not replenish recovery attempts.'}
