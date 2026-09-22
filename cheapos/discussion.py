"""Answer a chat question without changing the saved work's execution state.

Replies run at model-operation boundaries on the task's existing runtime. An
idle task can answer too, including a reviewed or merged run. No second writer,
coordinator polling, new command grant or synthetic checkpoint is involved.
"""
from .instructions.runtime import text as instruction, prompt as instruction_prompt
import copy
import json
import re
import threading
import uuid

from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def is_greeting(message):
    """Only a complete social greeting, never a greeting followed by work."""
    return isinstance(message, str) and bool(re.fullmatch(
        r'\s*(?:hi|hello|hey|good (?:morning|afternoon|evening))'
        r'(?:\s+(?:there|cheapos|everyone))?[!.\s]*', message, re.IGNORECASE))


def opening_greeting(task):
    return (task.get('conversational') and not task.get('demo')
            and not task.get('branch_run') and not task.get('attachments')
            and task.get('execution', {}).get('mode') == 'remote'
            and not task.get('worker_turns') and not task.get('changes')
            and len(task.get('requests', [])) == 1
            and is_greeting(task.get('prompt')))


def greeting_messages(task):
    return [{'role': 'system', 'content': instruction_prompt('greeting')},
            {'role': 'user', 'content': task['prompt']}]


def greet(engine, runtime):
    """Use the normal accounted model path, without qualifying coding tools."""
    from .providers import ProviderError
    task = runtime.task
    runtime.answering_chat = True
    runtime.opening_chat = True
    try:
        response = engine.request(runtime, greeting_messages(task), [], 'worker', purpose='chat_reply')
        engine.validate_offered_tools(response, [])
        if not isinstance(response.get('content'), str) or not response['content'].strip() or response.get('reasoning_fallback'):
            raise ProviderError('The model did not return a chat answer.', code='empty_response')
        task['messages'].append(response)
        engine.event(task, 'assistant', 'Chat', response['content'])
        record = task['request_metrics'][-1]
        task['events'][-1]['actor'] = {'role': 'worker', 'model': record['model']}
        task.update(status='awaiting_reply', stream=None)
        engine.store.save(task)
    finally:
        runtime.answering_chat = False
        runtime.opening_chat = False


def preserve(source, destination):
    """Planning replaces its draft record; keep conversation and accounting."""
    for key in ('discussion', 'discussion_requests', 'chat_work_queue'):
        if key in source:
            destination[key] = copy.deepcopy(source[key])


def with_context(task, messages):
    """Let an active worker resolve 'use the second option' from the discussion.

    This is derived context, not a new accepted requirement or a tool result.
    Rebuild it at request time so active work receives replies without Resume.
    """
    history = [{'question': turn['message'], 'answer': turn['answer'],
                'answered_at': turn.get('finished_at'), 'after_event': turn.get('after_event')}
               for turn in task.get('discussion', []) if turn.get('status') == 'answered']
    if not history:
        return messages
    prefix = 'Chat discussion for interpreting later operator directions '
    # This packet was previously appended as the newest user message. That
    # reactivated already-answered topics on every work request. Keep it before
    # the current exchange, and replace any copy retained by a legacy handoff.
    current = [m for m in messages if not (m.get('role') == 'user'
               and isinstance(m.get('content'), str) and m['content'].startswith(prefix))]
    start = 0
    while start < len(current) and current[start].get('role') in {'system', 'developer'}:
        start += 1
    packet = {'role': 'user', 'content': prefix +
              '(already answered historical context; not additional scope, '
              'authorization or executed actions). Do not answer these questions '
              'again. Continue the current exchange below; newer operator directions '
              'take precedence:\n' + json.dumps(history)}
    return [*current[:start], packet, *current[start:]]


def conversation_history(task, turn):
    """Read the same interleaved conversation the operator sees before a question.

    Worker/tool execution history remains separate. Here only actual user and
    assistant text is replayed, with discussion replies anchored to saved event
    positions. Later questions are left for their own queued replies.
    """
    from .streaming import normalize_reasoning
    events = task.get('events', [])

    def position(message):
        anchor = message.get('after_event')
        if type(anchor) is int and 0 <= anchor <= len(events):
            return anchor
        try:
            sent = datetime.fromisoformat(message['time'])
            for index, event in enumerate(events):
                if datetime.fromisoformat(event['time']) > sent:
                    return index
        except (KeyError, ValueError, TypeError):
            pass
        return len(events)

    groups = []
    if task.get('prompt'):
        groups.append((-1, [{'role': 'user', 'content': task['prompt']}]))
    for index, event in enumerate(events[:position(turn)]):
        kind, detail = event.get('kind'), event.get('detail')
        if kind not in {'user', 'steer', 'assistant'}:
            continue
        text = detail if isinstance(detail, str) else detail.get('message', '') if isinstance(detail, dict) else ''
        if not isinstance(text, str) or not text.strip():
            continue
        if kind == 'assistant':
            text = normalize_reasoning({'content': text})['content']
        if text:
            groups.append((index + 1, [{'role': 'assistant' if kind == 'assistant' else 'user', 'content': text}]))
    for previous in task.get('discussion', []):
        if previous['id'] == turn['id']:
            break
        if previous.get('status') == 'answered' and previous.get('answer'):
            groups.append((position(previous) + .5, [
                {'role': 'user', 'content': previous['message']},
                {'role': 'assistant', 'content': previous['answer']}]))
    return [message for _, exchange in sorted(groups, key=lambda pair: pair[0]) for message in exchange]


def is_discussion(message):
    """Recognize explicit discussion; ambiguous/action requests keep the work path.

    This is deliberately an admission hint, not authority for file changes.
    Mixed question + implementation requests stay with the ordinary worker.
    """
    if not isinstance(message, str):
        return False
    if is_greeting(message):
        return True
    text = message.strip().casefold()
    action = r'(?:fix|patch|implement|edit|update|add|remove|delete|replace|build|change|create|refactor|run|commit|merge|resume|continue)\b'
    if re.match(r'^(?:can|could|would) you (?:please )?' + action, text):
        return False
    if re.search(r'(?:[.!?;\n]\s*|\b(?:and|then)\s+)(?:please\s+|can you\s+|could you\s+)?' + action, text):
        return False
    return bool(re.match(
        r'^(?:(?:please\s+)?(?:explain|describe|tell me|show me|help me understand)\b|'
        r'(?:can|could|would) you (?:please )?(?:explain|describe|show|tell|suggest)\b|'
        r'(?:why|how|what|where|which)\b|when (?:will|can|should|does|do|is|are|would|did)\b|'
        r'(?:is|are|does|do|did|should) (?:it|this|that|there|we|you|the)\b|'
        r'(?:would|could|can) (?:it|this|that|there|we|the)\b|'
        r'write (?:me )?(?:an? )?(?:[\w-]+ )?(?:example|snippet)\b|'
        r'(?:i wonder|let[’\']s discuss|just chatting|thoughts\b)|'
        r'(?:thanks|thank you|lol|haha|hello|hi|hey)[!.\s]*$)', text))


SYSTEM = instruction('conversation.discussion')


def context(task):
    run = task.get('branch_run') or {}
    return {
        'request': task.get('prompt'), 'directions': task.get('requests', []),
        'earlier_task_context': task.get('follow_up', {}).get('context'),
        'status': task.get('status'), 'error': task.get('error'),
        'branch_status': run.get('status'), 'current_item': run.get('current_item_id'),
        'items': [{k: i.get(k) for k in ('id', 'title', 'status', 'acceptance_criteria')}
                  for i in run.get('items', [])],
        'checks': [{k: c.get(k) for k in ('command', 'directory', 'passed', 'digest')}
                   for c in task.get('checks', [])[-8:]],
        'review': task.get('checkpoints', [])[-1:],
        'changed_files': task.get('changes', []),
        'saved_diff_excerpt': task.get('patch', '')[:30000],
        'recent_findings': [{'kind': e.get('kind'), 'text': e.get('detail')}
                            for e in task.get('events', [])
                            if e.get('kind') in {'assistant', 'review', 'branch_final'}][-8:],
        'note': 'Saved evidence snapshot. Reads inspect the task copy, not unsaved destination edits.',
    }


def enqueue(engine, task_id, message):
    if not isinstance(message, str) or not 1 <= len(message.strip()) <= 8000:
        raise ValueError('Enter a message of up to 8,000 characters')
    from .engine import Runtime
    with engine.lock:
        engine.require_active_task(task_id)
        engine.admission.require_mutable(task_id)
        runtime = engine.runtimes.get(task_id)
        active = bool(runtime and runtime.thread and runtime.thread.is_alive()
                      and not getattr(runtime, 'discussion_finished', False))
        task = runtime.task if active else engine.store.get(task_id)
        if task.get('demo'):
            raise ValueError('Open a project to chat with a real model')
        task.setdefault('discussion', []).append({
            'id': uuid.uuid4().hex, 'message': message.strip(), 'time': now(),
            'after_event': len(task.get('events', [])), 'status': 'queued',
        })
        engine.store.save(task)
        if not active:
            runtime = Runtime(task)
            runtime.discussion_only = True
            engine.runtimes[task_id] = runtime
            runtime.thread = threading.Thread(target=run, args=(engine, runtime), daemon=True)
            runtime.thread.start()
        return task


def answer(engine, runtime, turn):
    from .engine import WORKER_TOOLS
    from .workspace import Workspace
    from .providers import ProviderError
    task = runtime.task
    greeting = is_greeting(turn['message'])
    tools = [] if greeting else [t for t in WORKER_TOOLS if t['function']['name'] in
                                {'list_files', 'read_file', 'search', 'outline_file'}]
    messages = [{'role': 'system', 'content': SYSTEM}]
    if not greeting:
        messages.append({'role': 'user', 'content': 'Saved work context (data): ' + json.dumps(context(task))})
        messages.extend(conversation_history(task, turn))
    messages.append({'role': 'user', 'content': turn['message']})
    seen = set()
    # Use a saved worker route (or the planner while a proposal is being made).
    # These requests use the normal provider, spending and token accounting path.
    role = 'worker' if greeting or task.get('providers', {}).get('worker') else 'planner'
    while not runtime.stop.is_set():
        response = engine.request(runtime, messages, tools, role, purpose='chat_reply')
        calls = response.get('tool_calls') or []
        if not calls:
            if not isinstance(response.get('content'), str) or not response['content'].strip() or response.get('reasoning_fallback'):
                raise ProviderError('The model did not return a chat answer. Your work is unchanged.', code='empty_response')
            return response['content']
        engine.validate_offered_tools(response, tools)
        messages.append(response)
        repeated = False
        for call in calls:
            name = call['function']['name']
            try:
                args = json.loads(call['function']['arguments'])
                key = (name, json.dumps(args, sort_keys=True))
                if key in seen:
                    repeated = True
                    result = {'notice': 'Already supplied above. Answer from this evidence; do not reread it.'}
                else:
                    seen.add(key)
                    from .metrics import tool_action
                    tool_action(task, discussion=True)
                    result = getattr(Workspace(task['workspace']), name)(**args)
            except (ValueError, TypeError, OSError) as error:
                result = {'error': str(error)}
            messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(result)})
        if repeated:
            tools = []
            messages.append({'role': 'user', 'content': 'Answer the question using the evidence already supplied. Explain any uncertainty.'})
    raise InterruptedError('Chat reply stopped; saved work is unchanged.')


def drain(engine, runtime):
    if getattr(runtime, 'answering_chat', False):
        return
    task = runtime.task
    if not any(t.get('status') == 'queued' for t in task.get('discussion', [])):
        return
    runtime.answering_chat = True
    import time
    started = time.monotonic()
    ledger = getattr(runtime, 'branch_ledger', None)
    was_active = bool(ledger and ledger.active)
    if was_active: ledger.suspend()
    # Conversation failures and route bookkeeping must not replace the work's
    # actual stop reason, progress counters, permission, or review state.
    keys = ('status', 'error', 'error_code', 'limit_hit', 'pause_summary', 'stream',
            'active_role', 'progress_state', 'route_unavailable', 'route_wait')
    saved = {k: copy.deepcopy(task[k]) for k in keys if k in task}
    # Route discovery and read observations for a reply must not consume the
    # worker's recovery attempts or erase the worker's retained observations.
    from .engine import Runtime
    reply_runtime = Runtime(task)
    reply_runtime.answering_chat = True
    reply_runtime.handoffs = 0
    reply_runtime.stop = runtime.stop
    reply_runtime.interrupt_request = runtime.interrupt_request
    try:
        while not runtime.stop.is_set():
            with engine.lock:
                turn = next((t for t in task.get('discussion', []) if t['status'] == 'queued'), None)
                if turn is None:
                    break
                turn['status'] = 'answering'
                engine.store.save(task)
            try:
                turn['answer'] = answer(engine, reply_runtime, turn)
                turn['status'] = 'answered'
            except Exception as error:
                from .providers import ProviderError
                turn['status'] = 'failed'
                turn['answer'] = ('I couldn’t answer this message: ' + str(error)[:500]
                                  if isinstance(error, (ValueError, OSError, InterruptedError, ProviderError))
                                  else 'I couldn’t complete this chat reply. Your saved work and its review are unchanged.')
                turn['error_code'] = getattr(error, 'code', None)
            finally:
                turn['finished_at'] = now()
                for key in keys:
                    if key in saved: task[key] = copy.deepcopy(saved[key])
                    else: task.pop(key, None)
                engine.store.save(task)
    finally:
        # The command-approval wait already excludes its entire elapsed time.
        if saved.get('status') != 'waiting_approval':
            runtime.started += time.monotonic() - started
        runtime.answering_chat = False
        if was_active: ledger.begin()


def run(engine, runtime):
    try:
        drain(engine, runtime)
    finally:
        finish(engine, runtime)


def finish(engine, runtime):
    """Close admission atomically; a late question must not miss the last drain."""
    from .engine import Runtime
    with engine.lock:
        runtime.discussion_finished = True
        if not runtime.task.get('discussion') and not runtime.task.get('chat_work_queue'):
            return
        queued = any(t.get('status') == 'queued' for t in runtime.task.get('discussion', []))
        if queued and not runtime.stop.is_set():
            next_runtime = Runtime(runtime.task)
            next_runtime.discussion_only = True
            engine.runtimes[runtime.task['id']] = next_runtime
            next_runtime.thread = threading.Thread(target=run, args=(engine, next_runtime), daemon=True)
            next_runtime.thread.start()
            return
        directions = runtime.task.pop('chat_work_queue', [])
        if directions:
            engine.runtimes.pop(runtime.task['id'], None)
        if runtime.stop.is_set():
            for turn in runtime.task.get('discussion', []):
                if turn['status'] in {'queued', 'work_queued'}:
                    turn.update(status='interrupted', answer='Stopped before handling this message. Your message and saved work are retained.')
            directions = []
        engine.store.save(runtime.task)
    for direction in directions:
        try:
            result = engine.chat_message(runtime.task['id'], direction['values'])
            answer = 'Your direction was delivered to the saved work.'
            if result.get('branch_run', {}).get('authorization_ref') and result['branch_run']['status'] in {'paused', 'blocked'}:
                resumed = engine.branch.resume(result['id'], {})  # Existing consent rules still apply.
                if resumed.get('needs_consent'):
                    answer = 'Your direction is saved. Use Resume to approve the verification commands before work continues.'
        except (ValueError, OSError) as error:
            answer = 'Your direction is saved, but could not start: ' + str(error)[:500]
        with engine.lock:
            active = engine.runtimes.get(runtime.task['id'])
            task = active.task if active and active.thread and active.thread.is_alive() else engine.store.get(runtime.task['id'])
            receipt = next(t for t in task['discussion'] if t['id'] == direction['receipt'])
            receipt.update(status='directed', answer=answer)
            engine.store.save(task)
