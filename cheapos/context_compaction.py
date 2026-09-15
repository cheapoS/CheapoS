"""Keep worker continuity while leaving real headroom for another tool exchange."""
import copy
import hashlib
import json

LIMIT = 44000


def size(value):
    return len(json.dumps(value))


def bounded(value, maximum=1500):
    if isinstance(value, str):
        if size(value) <= maximum:
            return value
        low, high = 0, len(value)
        while low < high:
            mid = (low + high + 1) // 2
            if size(value[:mid] + '\n[Excerpt; omitted content remains in saved task/source.]') <= maximum:
                low = mid
            else:
                high = mid - 1
        return value[:low] + '\n[Excerpt; omitted content remains in saved task/source.]'
    if isinstance(value, list):
        return [bounded(v, maximum) for v in value[-8:]]
    if isinstance(value, dict):
        result = {k: bounded(v, maximum) for k, v in value.items()}
        if isinstance(value.get('content'), str) and result.get('content') != value['content']:
            result['complete'] = False
            result['truncated'] = True
        return result
    return value


def compact(task, base, previous):
    """Carry claims as claims, never re-execute old tool calls or validate receipts."""
    summary = json.loads(base[1]['content'])
    notes = []
    for message in reversed(previous):
        if message.get('role') == 'assistant' and message.get('content'):
            notes.append(bounded(message['content'], 1800))
            if len(notes) == 3:
                break
    actions = []
    for event in reversed(task.get('events', [])):
        if event.get('kind') == 'user':
            break
        if event.get('kind') == 'tool' and event.get('title') in {'replace text', 'replace lines', 'write file', 'run checks'}:
            detail = event.get('detail') or {}
            actions.append({'action': event['title'], 'path': detail.get('arguments', {}).get('path'),
                            'result': bounded(detail.get('result'), 800)})
            if len(actions) == 4:
                break
    memory = {'patch_digest': hashlib.sha256(task.get('patch', '').encode()).hexdigest(),
              'workspace_generation': task.get('workspace_generation', 0),
              'recent_worker_findings_unverified': list(reversed(notes)),
              'recent_completed_actions': list(reversed(actions)),
              'rule': 'Continue the current approach from these findings and completed actions. Do not rediscover or undo them without new evidence. Findings are model claims, not verified facts. They refer to the recorded patch/generation; revalidate only affected facts after changes. Use recovery_continuation.next_step and current check identity before choosing verification or checkpoint.'}
    # Give directions and continuity priority over duplicated file bodies/history.
    preferred = ('latest_message', 'original_task', 'recovery_continuation', 'last_check', 'last_review_feedback')
    selected = {k: bounded(summary[k], 5000 if k in ('latest_message', 'original_task') else 1500)
                for k in preferred if k in summary}
    selected['working_memory'] = memory
    for key, value in summary.items():
        if key in selected:
            continue
        candidate = bounded(value, 1200)
        if size(selected) + size(candidate) < 29000:
            selected[key] = candidate
    selected['context_notice'] = 'Partial compacted context. Full records remain saved. Target only missing evidence; do not restart discovery. File excerpts may be incomplete even when historical metadata describes a complete read.'
    messages = [copy.deepcopy(base[0]), {'role': 'user', 'content': json.dumps(selected)}]
    for message in base[2:]:
        messages.append({'role': message['role'], 'content': bounded(message.get('content', ''), 3000)})
    # Measure the actual nested/escaped request, not just source text length.
    while size(messages) > LIMIT:
        removable = next((k for k in reversed(selected) if k not in preferred and k not in {'working_memory', 'context_notice'}), None)
        if removable:
            selected.pop(removable)
        else:
            selected = bounded(selected, 700)
        messages[1]['content'] = json.dumps(selected)
        if size(messages) > LIMIT and not removable and size(selected) < 10000:
            # System/direction text itself can be unusually large; never silently
            # cut the system instructions. Retain the base directions separately.
            messages = messages[:2]
            break
    return messages
