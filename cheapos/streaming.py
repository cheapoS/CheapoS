"""Bounded OpenAI-compatible SSE assembly. Partial tool calls never execute."""
import json
import re
import time

MAX_RESPONSE_BYTES = 4_000_000
STREAM_MAX_SECONDS = 600


def read_chat_stream(response, emit, stopped, error_type, max_seconds=STREAM_MAX_SECONDS):
    started = time.monotonic()
    content, thinking, calls, usage = [], [], {}, {}
    size, finished, done = 0, False, False
    frame = []

    def consume(payload):
        nonlocal usage, finished, done
        if payload.strip() == '[DONE]':
            done = True
            return
        data = json.loads(payload)
        if not isinstance(data, dict) or data.get('error'):
            raise error_type('The model reported an error while streaming.', code='stream_error')
        if isinstance(data.get('usage'), dict):
            usage = data['usage']
        for choice in data.get('choices', []):
            if choice.get('index', 0) != 0:
                continue
            reason = choice.get('finish_reason')
            if reason is not None:
                if reason == 'length':
                    raise error_type('The model reached its output limit before finishing. Partial tool calls were not executed.', code='output_limit')
                if not isinstance(reason, str) or reason not in {'stop', 'tool_calls', 'function_call'}:
                    label = reason if isinstance(reason, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', reason) else 'unrecognized'
                    raise error_type(f'The provider ended the response with finish_reason={label}. Partial tool calls were not executed; saved files are unchanged by this response.', code='stream_error')
                finished = True
            delta = choice.get('delta') or {}
            thought = delta.get('reasoning') or delta.get('reasoning_content') or delta.get('thinking')
            if isinstance(thought, str) and thought:
                thinking.append(thought)
                emit('thinking', thought)
            answer = delta.get('content')
            if isinstance(answer, str) and answer:
                content.append(answer)
                emit('answer', answer)
            for fragment in delta.get('tool_calls') or []:
                index = fragment.get('index', 0)
                if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < 8:
                    raise error_type('The model streamed an invalid tool call.')
                call = calls.setdefault(index, {'id':'', 'type':'function', 'function':{'name':'', 'arguments':''}})
                if fragment.get('id'):
                    call['id'] = fragment['id']
                function = fragment.get('function') or {}
                for key in ['name', 'arguments']:
                    if key in function:
                        if not isinstance(function[key], str):
                            raise error_type('The model streamed an invalid tool call.')
                        call['function'][key] += function[key]
                emit('tool', call['function']['name'])

    while not done:
        if stopped():
            raise InterruptedError('Stopped while receiving the model response')
        if time.monotonic() - started > max_seconds:
            raise error_type(f'The model stream exceeded {max_seconds} seconds. Partial tool calls were not executed.', code='stream_timeout')
        line = response.readline(MAX_RESPONSE_BYTES + 1)
        if not line:
            if frame:
                consume('\n'.join(frame))
            break
        size += len(line)
        if size > MAX_RESPONSE_BYTES:
            raise error_type('Provider response exceeded 4 MB')
        line = line.decode('utf-8').rstrip('\r\n')
        if not line:
            if frame:
                consume('\n'.join(frame))
                frame = []
        elif line.startswith('data:'):
            frame.append(line[5:].lstrip(' '))
    if not done or not finished:
        raise error_type('The model stream ended before its response was complete. Partial tool calls were not executed.', code='stream_interrupted')
    message = {'role':'assistant', 'content':''.join(content) or None}
    if thinking:
        message['reasoning'] = ''.join(thinking)
    if calls:
        message['tool_calls'] = [calls[index] for index in sorted(calls)]
        for call in message['tool_calls']:
            if not call['id'] or not call['function']['name'] or not isinstance(json.loads(call['function']['arguments']), dict):
                raise error_type('The model streamed an incomplete tool call.')
    return {'choices':[{'message':message}], 'usage':usage}
