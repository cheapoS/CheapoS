"""Bounded OpenAI-compatible SSE assembly. Partial tool calls never execute."""
import json
import re
import time
from .served_identity import safe_model

MAX_RESPONSE_BYTES = 4_000_000
STREAM_MAX_SECONDS = 600


def read_chat_stream(response, emit, stopped, error_type, max_seconds=STREAM_MAX_SECONDS):
    started = time.monotonic()
    content, thinking, calls, usage = [], [], {}, {}
    size, finished, done, limited = 0, False, False, False
    frame = []
    reported_model = None
    identity_conflict = False

    def consume(payload):
        nonlocal usage, finished, done, limited, reported_model, identity_conflict
        if payload.strip() == '[DONE]':
            done = True
            return
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as error:
            raise error_type(f'The provider sent malformed JSON in a stream event ({error.msg}, line {error.lineno}, column {error.colno}). No tool calls from this response were executed.', code='invalid_stream_json') from None
        if isinstance(data, dict) and isinstance(data.get('usage'), dict):
            usage = data['usage']
        if not isinstance(data, dict) or data.get('error'):
            # Gateways can deliver quota failures inside HTTP-200 SSE frames.
            # Recognize this narrow provider signal without echoing a raw body
            # that may contain account details. Do not guess a reset time.
            failure = data.get('error') if isinstance(data, dict) else None
            detail = failure.get('message', '') if isinstance(failure, dict) else failure
            if isinstance(detail, str) and 'free-models-per-day' in detail.lower():
                raise error_type('The provider daily free-model quota is exhausted. Retry after the provider resets it; no reset time was supplied.', code='gateway_cooldown', scope='provider')
            if isinstance(failure, dict) and (failure.get('type') == 'rate_limit_error' or failure.get('code') == 'rate_limit_exceeded'):
                # A connection can have separate model quota pools. Without an
                # explicit provider-wide signal, do not exclude every model.
                raise error_type('The model route reported a rate limit or exhausted quota. Retry when its allowance resets; the stream supplied no reset time. Partial tool calls were not executed.', code='gateway_cooldown', scope='model')
            if isinstance(failure, dict) and failure.get('code') in {'streaming_unsupported', 'unsupported_streaming'}:
                raise error_type('The route explicitly reports that streaming is unsupported.', code='streaming_unsupported', usage=usage or None)
            raise error_type('The model reported an error while streaming.', code='stream_error', usage=usage or None)
        if 'model' in data:
            model=safe_model(data['model'])
            if model is None or reported_model is not None and model!=reported_model:identity_conflict=True
            elif reported_model is None:reported_model=model
        if isinstance(data.get('usage'), dict):
            usage = data['usage']
        for choice in data.get('choices', []):
            if choice.get('index', 0) != 0:
                continue
            reason = choice.get('finish_reason')
            if reason is not None:
                if reason == 'length':
                    # Drain the bounded stream for its final usage frame. No
                    # message/tool calls from a limited response will be returned.
                    limited = True
                elif not isinstance(reason, str) or reason not in {'stop', 'tool_calls', 'function_call'}:
                    label = reason if isinstance(reason, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', reason) else 'unrecognized'
                    raise error_type(f'The provider ended the response with finish_reason={label}. Partial tool calls were not executed; saved files are unchanged by this response.', code='stream_error' if label == 'error' else 'model_refusal', usage=usage or None)
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
                    raise error_type('The model streamed an invalid tool call.', code='invalid_tool_envelope')
                call = calls.setdefault(index, {'id':'', 'type':'function', 'function':{'name':'', 'arguments':''}})
                if fragment.get('id'):
                    call['id'] = fragment['id']
                function = fragment.get('function') or {}
                for key in ['name', 'arguments']:
                    if key in function:
                        if not isinstance(function[key], str):
                            raise error_type('The model streamed an invalid tool call.', code='invalid_tool_envelope')
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
            raise error_type('Provider response exceeded 4 MB', code='response_too_large')
        line = line.decode('utf-8').rstrip('\r\n')
        if not line:
            if frame:
                consume('\n'.join(frame))
                frame = []
        elif line.startswith('data:'):
            val = line[5:].lstrip(' ')
            if val.strip() == '[DONE]':
                if frame:
                    consume('\n'.join(frame))
                    frame = []
                done = True
                break
            frame.append(val)
    if limited:
        raise error_type('The model reached its output limit before finishing. Partial tool calls were not executed.', code='output_limit', usage=usage or None)
    if not done or not finished:
        raise error_type('The model stream ended before its response was complete. Partial tool calls were not executed.', code='stream_interrupted', usage=usage or None)
    message = {'role':'assistant', 'content':''.join(content) or None}
    if thinking:
        message['reasoning'] = ''.join(thinking)
    if calls:
        message['tool_calls'] = [calls[index] for index in sorted(calls)]
        for call in message['tool_calls']:
            if not isinstance(call['id'], str) or not call['id'] or not call['function']['name']:
                raise error_type('The model streamed a tool call without a valid ID or name.', code='invalid_tool_envelope')
            # The complete response is accounted before the controller validates
            # argument JSON. Invalid arguments become tool feedback, never edits.
    return {'choices':[{'message':message}], 'usage':usage, 'model':None if identity_conflict else reported_model}
