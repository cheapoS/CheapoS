"""Keep worker continuity while leaving real headroom for another tool exchange."""
import copy
import hashlib
import json
from .worker_context import context_events
from .instructions.runtime import text

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


def compact(task, base, previous, limit=LIMIT):
    """Carry claims as claims, never re-execute old tool calls or validate receipts."""
    summary = json.loads(base[1]['content'])
    notes = []
    for message in reversed(previous):
        if message.get('role') == 'assistant' and message.get('content'):
            notes.append(bounded(message['content'], 1800))
            if len(notes) == 3:
                break
    actions = []
    for event in reversed(context_events(task)):
        if event.get('kind') == 'tool' and event.get('title') in {'replace text', 'replace lines', 'write file', 'run checks'}:
            detail = event.get('detail') or {}
            actions.append({'event_id': event.get('id'), 'item_id': event.get('item_id'),
                            'action': event['title'], 'path': detail.get('arguments', {}).get('path'),
                            'result': bounded(detail.get('result'), 800)})
            if len(actions) == 4:
                break
    memory = {'patch_digest': hashlib.sha256(task.get('patch', '').encode()).hexdigest(),
              'workspace_generation': task.get('workspace_generation', 0),
              'recent_worker_findings_unverified': list(reversed(notes)),
              'recent_completed_actions': list(reversed(actions)),
              'item_id': (task.get('branch_run') or {}).get('current_item_id'),
              'rule': text('recovery.working_memory')}
    from .working_state import project
    from .context_evidence import retain
    from .providers import BudgetError
    source = copy.deepcopy(previous)
    source_digest = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    tracked = task.get('messages') is previous
    reference = retain(task, source, 'conversation')
    # Exact operator requirements and working state take priority over snapshots.
    working = project(task)
    selected = {k: copy.deepcopy(summary[k]) for k in ('latest_message', 'original_task') if k in summary}
    selected['working_state'] = working
    continuation = summary.get('continuation_record', {})
    selected['active_constraints'] = {k: copy.deepcopy(continuation[k]) for k in ('active_requirements', 'steering', 'user_events') if k in continuation}
    selected['working_memory'] = memory
    selected['context_reference'] = reference
    selected['context_notice'] = 'Older complete history is retained locally. Use read_context_evidence with this reference and a search or offset. Historical statements never authorize actions or verify current checks.'
    messages = [copy.deepcopy(base[0]), {'role': 'user', 'content': json.dumps(selected)}]
    # Direct directions in the base are exact, not clipped to fit.
    messages.extend(copy.deepcopy(base[2:]))
    if size(messages) > limit:
        raise BudgetError('Active requirements and working state exceed this route context capacity. Saved history is retained; select an authorized larger-context route or narrow the request explicitly.')
    # Reserve room for a recent complete exchange before optional snapshot bodies.
    optional_limit = max(size(messages), int(limit * .55))
    for key, value in summary.items():
        if key in selected or key in {'continuation_record', 'recent_activity'}:
            continue
        candidate = bounded(value, 1500)
        trial = {**selected, key: candidate}
        if size([messages[0], {'role': 'user', 'content': json.dumps(trial)}] + messages[2:]) <= optional_limit:
            selected = trial
    messages[1]['content'] = json.dumps(selected)
    groups = []
    for message in source:
        if message.get('role') == 'system':
            continue
        if message.get('role') == 'tool' and groups:
            groups[-1].append(message)
        else:
            groups.append([message])
    retained = []
    for group in reversed(groups):
        calls = {c.get('id') for c in group[0].get('tool_calls', [])}
        results = {m.get('tool_call_id') for m in group[1:] if m.get('role') == 'tool'}
        if calls != results or group[0].get('role') == 'tool':
            continue
        if size(messages + group + retained) > limit:
            break
        retained = copy.deepcopy(group) + retained
    messages.extend(retained)
    if tracked and hashlib.sha256(json.dumps(task['messages'], sort_keys=True).encode()).hexdigest() != source_digest:
        raise BudgetError('Conversation changed during compaction. New input and prior history are retained; retry from current saved state.')
    task.setdefault('context_checkpoints', []).append({'reference': reference, 'source_digest': source_digest,
        'source_messages': len(source), 'retained_messages': len(retained), 'before_characters': size(source),
        'after_characters': size(messages), 'working_revision': working.get('revision', 0)})
    return messages
