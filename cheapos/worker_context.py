"""Select current worker context without relabeling task-wide history."""
import json

from .instructions.runtime import text


def active_events(task):
    """Explicit item ownership wins; legacy events need an item-start boundary."""
    events = task.get('events', [])
    item = (task.get('branch_run') or {}).get('current_item_id')
    if not item:
        boundary = max((i for i, e in enumerate(events) if e.get('kind') == 'user'), default=-1)
        return events[boundary + 1:]
    boundary = max((i for i, e in enumerate(events)
                    if e.get('kind') == 'branch_item'
                    and isinstance(e.get('detail'), dict)
                    and e['detail'].get('item_id') == item), default=len(events))
    return [event for i, event in enumerate(events)
            if event.get('item_id') == item or
            (not event.get('item_id') and i > boundary)]


def repeated_read_guidance(task):
    from . import work_policy
    from .continuation_policy import is_implementation
    work = (work_policy.active_implementation(task) or
            (not work_policy.read_only(task) and is_implementation(task)))
    return text('recovery.repeated_read_work' if work else 'recovery.repeated_read_research')


def read_notice(value):
    if not isinstance(value, str):
        return False
    return (value.startswith('This read returned the same information twice. Answer the user') or
            value in {text('recovery.repeated_read_work'), text('recovery.repeated_read_research')})


def clear_read_guidance(task):
    """Useful work supersedes a read warning, never other recovery/operator guidance."""
    if read_notice(task.get('loop_guidance')):
        task['loop_guidance'] = None


def refresh_read_guidance(task):
    """Retain obsolete notices by reference; deliver one current phase-specific rule.

    Only controller-generated read notices change. Tool observations, calls,
    user directions, failure attempts and verification receipts are untouched.
    """
    from .context_evidence import retain
    from .worker_conversation import append_direction
    if read_notice(task.get('loop_guidance')):
        task['loop_guidance'] = repeated_read_guidance(task)
    prefixes = ('Controller direction: ', 'CURRENT RECOVERY DIRECTION: ')
    messages = task.setdefault('messages', [])
    projected = []
    references = []
    def historical(value):
        if isinstance(value, list):
            return [historical(v) for v in value]
        if not isinstance(value, dict):
            return value
        result = {k: historical(v) for k, v in value.items()}
        if read_notice(result.get('guidance')):
            result['historical_guidance_reference'] = retain(task, result.pop('guidance'), 'workerread_notice')
        return result
    for message in messages:
        content = message.get('content', '')
        if message.get('role') == 'user' and isinstance(content, str) and any(
                content.startswith(prefix) and read_notice(content[len(prefix):]) for prefix in prefixes):
            # Keep an already-current notice in place; repeated assembly is stable.
            if content == 'CURRENT RECOVERY DIRECTION: ' + (task.get('loop_guidance') or '') and not any(
                    m.get('content') == content for m in projected):
                projected.append(message)
            else:
                references.append(retain(task, message, 'workerread_notice'))
            continue
        if message.get('role') in {'user', 'tool'}:
            try:
                value = json.loads(content)
            except (ValueError, TypeError):
                value = None
            updated = historical(value)
            if updated != value:
                references.append(retain(task, message, 'workerread_notice'))
                message = {**message, 'content': json.dumps(updated)}
        projected.append(message)
    task['messages'] = projected
    if references:
        saved = task.setdefault('worker_context_refresh', {}).setdefault('notice_references', [])
        saved.extend(ref for ref in references if ref not in saved)
    append_direction(projected, 'CURRENT RECOVERY DIRECTION: ', task.get('loop_guidance'))
