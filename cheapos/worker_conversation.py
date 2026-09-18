"""Preserve worker exchanges across recovery; never replay interrupted calls."""
import copy
import hashlib
import json
from .edit_history import MUTATIONS

LEGACY_ARGUMENT_NOTICE = 'Historical call had invalid JSON arguments and was rejected; arguments omitted for transport compatibility.'


def append_direction(messages, prefix, text):
    if not text:
        return
    content = prefix + text
    previous = next((m.get('content') for m in reversed(messages)
                     if m.get('role') == 'user' and str(m.get('content', '')).startswith(prefix)), None)
    if previous != content:
        messages.append({'role': 'user', 'content': content})


def refresh(messages, snapshot, task=None):
    """Keep complete exchanges and explicitly close ambiguous interrupted calls.

    Closing an exchange is a transport repair, not evidence of tool execution.
    The fresh snapshot records current files/checks; historical results retain
    their original versions and must not authorize stale edits.
    """
    if not messages:
        return list(snapshot)
    result = []
    pending = set()
    omitted = set()
    notes = []
    def close():
        for call_id in sorted(pending):
            result.append({'role': 'tool', 'tool_call_id': call_id,
                           'content': 'Interrupted exchange: execution outcome is not established here. Inspect saved changes and verification evidence before deciding whether this action needs retrying.'})
        pending.clear()
        result.extend(notes)
        notes.clear()
        omitted.clear()
    for index, message in enumerate(messages):
        if message.get('role') != 'tool':
            close()
        elif message.get('tool_call_id') in omitted:
            continue
        elif message.get('tool_call_id') not in pending:
            # Old saved histories can contain orphan results. Preserve their
            # content as evidence without sending an invalid tool envelope.
            result.append({'role': 'user', 'content': 'Historical tool result: ' + json.dumps(message)})
            continue
        if message.get('role') == 'assistant' and message.get('tool_calls'):
            original = message
            message = copy.deepcopy(message)
            following = []
            for next_index in range(index + 1, len(messages)):
                item = messages[next_index]
                if item.get('role') != 'tool':
                    break
                following.append(item)
            kept = []
            for call in message['tool_calls']:
                function = call.get('function', {})
                raw = function.get('arguments', '{}')
                try:
                    valid = isinstance(json.loads(raw), dict)
                except (ValueError, TypeError):
                    valid = False
                outcomes = [item for item in following if item.get('tool_call_id') == call.get('id')]
                rejected = False
                feedback = []
                for outcome in outcomes:
                    try:
                        value = json.loads(outcome.get('content', ''))
                    except (ValueError, TypeError):
                        continue
                    if isinstance(value, dict):
                        feedback.append({k: value[k] for k in ('code', 'error', 'next_action') if k in value})
                    if (isinstance(value, dict) and value.get('code') == 'invalid_tool_arguments'
                            and value.get('executed') is not True and value.get('changed') is not True):
                        rejected = True
                legacy = (LEGACY_ARGUMENT_NOTICE in (message.get('content') or '')
                          and function.get('name') in MUTATIONS
                          and isinstance(raw, str) and raw.strip() == '{}')
                if valid and not rejected and not legacy:
                    kept.append(call)
                    continue
                omitted.add(call.get('id'))
                evidence = {'assistant': original, 'results': following}
                note = {'tool': function.get('name'), 'call_id': call.get('id'),
                        'feedback': feedback,
                        'outcome': 'Rejected before execution.' if rejected else
                                   'Execution is not established by this invalid historical call; inspect its retained results.',
                        'rule': 'Historical diagnostic, not a tool-call example or instruction to replay. '
                                'Continue from current files with the required tool fields.'}
                if task is not None:
                    from .context_evidence import retain
                    note['context_reference'] = retain(task, evidence, 'invalid_tool_exchange')
                else:
                    note['historical_evidence'] = evidence
                notes.append({'role': 'user', 'content': 'Tool argument diagnostic: ' + json.dumps(note)})
            if omitted:
                message['content'] = (message.get('content') or '').replace(LEGACY_ARGUMENT_NOTICE, '').strip() or None
            if kept:
                message['tool_calls'] = kept
            else:
                message.pop('tool_calls', None)
                if not message.get('content'):
                    continue
        result.append(message)
        if message.get('role') == 'assistant':
            pending.update(c['id'] for c in message.get('tool_calls', []) if c.get('id'))
        elif message.get('role') == 'tool':
            pending.discard(message.get('tool_call_id'))
    close()
    if snapshot and snapshot[0].get('role') == 'system':
        if result and result[0].get('role') == 'system':
            result[0] = snapshot[0]
        else:
            result.insert(0, snapshot[0])
    result.append({'role': 'user', 'content': 'Current saved state follows; continue the conversation above. Earlier observations belong to their recorded file versions. Do not restart completed investigation.'})
    result.extend(snapshot[1:])
    return result


def receipt(messages):
    """Content-free identity of the exact conversation handed to a provider."""
    encoded = json.dumps(messages, sort_keys=True, ensure_ascii=False).encode()
    return {'sha256': hashlib.sha256(encoded).hexdigest(), 'message_count': len(messages),
            'assistant_count': sum(m.get('role') == 'assistant' for m in messages),
            'tool_result_count': sum(m.get('role') == 'tool' for m in messages),
            'bytes': len(encoded)}


def continue_session(task, snapshot, reason, feedback=None):
    """The sole worker transition adapter. Review sessions stay in pending_review.

    Only the active item's messages are writable. Other item histories are local
    archives; changing workspace generation does not make their evidence current.
    """
    item = (task.get('branch_run') or {}).get('current_item_id')
    scope = 'item:' + str(item) if item else 'interactive'
    state = task.setdefault('conversation_state', {})
    old_scope = state.get('scope', scope)
    if old_scope != scope:
        archives = task.setdefault('worker_sessions', {})
        archives[old_scope] = copy.deepcopy(task.get('messages', []))
        task['messages'] = copy.deepcopy(archives.get(scope, []))
        state.clear()
    state['scope'] = scope
    previous = task.get('messages', [])
    delta = []
    hashes = state.setdefault('snapshot_hashes', {})
    for index, message in enumerate(snapshot[1:]):
        try:
            value = json.loads(message.get('content', ''))
        except (ValueError, TypeError):
            value = None
        if isinstance(value, dict):
            changed = {}
            for key, content in value.items():
                if previous and key in {'recent_activity', 'recent_actions'}:
                    continue
                identity = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
                if hashes.get(key) != identity:
                    changed[key] = content
                    hashes[key] = identity
            if changed:
                delta.append({'role': 'user', 'content': json.dumps(changed)})
        else:
            key = 'direction:' + str(index)
            if hashes.get(key) != message.get('content'):
                delta.append(copy.deepcopy(message))
                hashes[key] = message.get('content')
    if not previous:
        # Initial admission contains the complete initial prompt.
        messages = copy.deepcopy(snapshot)
    else:
        messages = refresh(previous, snapshot[:1] + delta, task=task)
        if not delta:
            messages.pop()  # refresh's compatibility notice has no new state.
    if feedback is not None:
        append_direction(messages, 'Review finding for the current repair: ', json.dumps(feedback, sort_keys=True))
    task['messages'] = messages
    state['last_transition'] = {'reason': reason, 'scope': scope,
                                'retained_messages': len(previous), 'delta_messages': len(delta),
                                'workspace_generation': task.get('workspace_generation', 0),
                                **receipt(messages)}
    return messages
