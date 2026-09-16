"""Preserve worker exchanges across recovery; never replay interrupted calls."""
import copy
import hashlib
import json


def append_direction(messages, prefix, text):
    if not text:
        return
    content = prefix + text
    previous = next((m.get('content') for m in reversed(messages)
                     if m.get('role') == 'user' and str(m.get('content', '')).startswith(prefix)), None)
    if previous != content:
        messages.append({'role': 'user', 'content': content})


def refresh(messages, snapshot):
    """Keep complete exchanges and explicitly close ambiguous interrupted calls.

    Closing an exchange is a transport repair, not evidence of tool execution.
    The fresh snapshot records current files/checks; historical results retain
    their original versions and must not authorize stale edits.
    """
    if not messages:
        return list(snapshot)
    result = []
    pending = set()
    def close():
        for call_id in sorted(pending):
            result.append({'role': 'tool', 'tool_call_id': call_id,
                           'content': 'Interrupted exchange: execution outcome is not established here. Inspect saved changes and verification evidence before deciding whether this action needs retrying.'})
        pending.clear()
    for message in messages:
        if message.get('role') != 'tool':
            close()
        elif message.get('tool_call_id') not in pending:
            # Old saved histories can contain orphan results. Preserve their
            # content as evidence without sending an invalid tool envelope.
            result.append({'role': 'user', 'content': 'Historical tool result: ' + json.dumps(message)})
            continue
        if message.get('role') == 'assistant' and message.get('tool_calls'):
            message = copy.deepcopy(message)
            for call in message['tool_calls']:
                function = call.get('function', {})
                try:
                    valid = isinstance(json.loads(function.get('arguments', '{}')), dict)
                except (ValueError, TypeError):
                    valid = False
                if not valid:
                    function['arguments'] = '{}'
                    message['content'] = (message.get('content') or '') + '\nHistorical call had invalid JSON arguments and was rejected; arguments omitted for transport compatibility.'
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
        messages = refresh(previous, snapshot[:1] + delta)
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
