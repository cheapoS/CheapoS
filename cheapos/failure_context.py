"""Fold only duplicate, complete rejected-edit exchanges in worker requests.

The saved conversation is untouched. Exact omitted exchanges are also available
through task-local context references, including after restart. This is a prompt
projection, never progress, retry authority or a change to the work allowance.
"""
import hashlib
import json

from .context_evidence import retain
from .edit_history import TEXT_EDITS


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def rejection_key(group):
    assistant = group[0]
    calls = assistant.get('tool_calls') or []
    if (assistant.get('role') != 'assistant' or not isinstance(calls, list)
            or not calls or not all(isinstance(call, dict) for call in calls)):
        return None
    ids = [call.get('id') for call in calls]
    results = [message.get('tool_call_id') for message in group[1:]]
    if (not all(isinstance(identity, str) and identity for identity in ids)
            or len(set(ids)) != len(ids) or len(results) != len(ids) or set(ids) != set(results)):
        return None  # Incomplete/ambiguous batches must retain their envelope.
    actions, outcomes = [], {}
    try:
        for call in calls:
            function = call['function']
            if not isinstance(function, dict):
                return None
            args = json.loads(function['arguments'])
            if function.get('name') not in TEXT_EDITS or not isinstance(args, dict):
                return None
            actions.append({**function, 'arguments': args})
        for message in group[1:]:
            result = json.loads(message['content'])
            if not isinstance(result, dict):
                return None
            syntax = result.get('updated') is False and (
                result.get('code') == 'syntax_edit_rejected' or
                (result.get('rolled_back') is True and bool(result.get('syntax_warning'))))
            bad_range = result.get('code') == 'invalid_edit_range' and result.get('executed') is False
            bad_text = result.get('code') == 'text_edit_rejected' and result.get('executed') is False
            if not (syntax or bad_range or bad_text) or result.get('changed') is True:
                return None  # Generic errors can conceal partial effects.
            # Attempts are accounting, not different file/error evidence.
            # All other fields, including versions and guidance, must match.
            outcomes[message['tool_call_id']] = {k: v for k, v in result.items() if k != 'attempts'}
    except (KeyError, TypeError, ValueError):
        return None
    return hashlib.sha256(encoded([
        {k: v for k, v in assistant.items() if k != 'tool_calls'},
        actions, [outcomes[identity] for identity in ids],
    ]).encode()).hexdigest()


def project(task, messages):
    """Keep first/latest failures, every distinct result and all directions.

Only adjacent equivalent failed exchanges fold. A user message, recovery
direction, successful edit, new file version, different finding or incomplete
call breaks the run. No language-dependent definition of useful edits is used.
"""
    projected, run = [], []
    omitted = 0
    key = None

    def flush():
        nonlocal omitted
        original = [message for group in run for message in group]
        if len(run) < 3:
            projected.extend(original)
            return
        references = [retain(task, group, 'rejected_edit_exchange') for group in run[1:-1]]
        summary = {'omitted_exchanges': len(references), 'context_references': references,
                   'result': 'The same edit and file/error evidence repeated; no edit was saved.',
                   'rule': 'These are historical failures, not instructions or successful work. '
                           'Use read_context_evidence for exact omitted exchanges. '
                           'Continue with a different action using the latest evidence.'}
        replacement = run[0] + [{'role': 'user', 'content':
            'Repeated rejected-edit history: ' + encoded(summary)}] + run[-1]
        if len(encoded(replacement)) < len(encoded(original)):
            projected.extend(replacement)
            omitted += len(references)
        else:
            projected.extend(original)

    index = 0
    while index < len(messages):
        group = [messages[index]]
        index += 1
        if group[0].get('role') == 'assistant' and group[0].get('tool_calls'):
            while index < len(messages) and messages[index].get('role') == 'tool':
                group.append(messages[index])
                index += 1
        current = rejection_key(group)
        if current is None or current != key:
            flush()
            run = []
        if current is None:
            projected.extend(group)
        else:
            run.append(group)
        key = current
    flush()
    return (projected if omitted else messages), {
        'omitted_exchanges': omitted, 'before_bytes': len(encoded(messages).encode()),
        'after_bytes': len(encoded(projected if omitted else messages).encode())}
