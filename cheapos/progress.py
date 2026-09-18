"""Request-scoped durable progress and recovery evidence, without model claims."""
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def state(task):
    segment = len(task.get('requests', [task.get('prompt', '')]))
    value = task.get('progress_state')
    if not value or value.get('segment') != segment:
        value = {'segment': segment, 'revision': 0, 'seen': {digest(item): True for item in candidates(task)},
                 'handoffs': 0, 'malformed_attempts': 0, 'answer_attempts': 0}
        task['progress_state'] = value
    elif isinstance(value.get('seen'), list):
        # Migrate saved histories without renewing progress or losing cycles.
        # An exact index grows with real work; saturation is not a work limit.
        value['seen'] = dict.fromkeys(value['seen'], True)
    return value


def candidates(task):
    candidates = [['patch', task.get('workspace_generation', 0), task.get('patch', '')]]
    if task.get('checks'):
        check = task['checks'][-1]
        # Successful output commonly varies only in elapsed time. A new log is
        # not new progress for the same verified inputs and command. Failed
        # output remains useful evidence for diagnosing a changed failure.
        output = None if check.get('passed') else check.get('output')
        candidates.append(['check', check.get('generation', 0), check.get('digest'), check.get('command'), check.get('outcome'), check.get('passed'), output, check.get('verification_identity')])
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
            value['seen'][key] = True
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
    from .coordinator_recovery import episode_key
    assistance = next((e for e in task.get('coordinator_recovery', []) if e.get('key') == episode_key(task)), None)
    if assistance:
        attempts.append('coordinator assistance: ' + (assistance.get('summary') or assistance['state']))
    return {'blocker': str(blocker), 'attempted': attempts,
            'saved_files': [f['path'] for f in task.get('changes', [])],
            'check': {'command': check.get('command', []), 'passed': check.get('passed'), 'outcome': check.get('outcome')},
            'next_action': 'Your saved work can be inspected in Details. You can change the approach in Chat or inspect model settings. Resume alone does not replenish recovery attempts.'}


def inspection(task, path, version, lines):
    """A newly observed source range is evidence; rereads and clocks are not."""
    value=state(task)
    inspected=value.setdefault('inspected', {})
    key=digest([path,version])
    old=set(inspected.get(key,[]))
    new=set(lines)-old
    if not new:return False
    inspected[key]=sorted(old|new)
    value['revision']+=1
    return True
