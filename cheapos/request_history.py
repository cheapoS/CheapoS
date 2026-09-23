"""Lossless wire representation of rejected historical tool arguments."""
import copy
import json


def _non_json_constant(value):
    raise ValueError('Non-JSON number')


def project(messages):
    """Keep call/result IDs and raw diagnostics without resending invalid JSON.

    This projects prior messages only; it never repairs or executes a new call.
    Providers validate historical arguments before generating the next response.
    An explicit diagnostic object keeps rejected bytes available to the model,
    while the original task history and the paired error receipt stay unchanged.
    """
    result = copy.deepcopy(messages)
    for message in result:
        if message.get('role') != 'assistant':
            continue
        for call in message.get('tool_calls') or []:
            function = call.get('function') if isinstance(call, dict) else None
            if not isinstance(function, dict):
                continue  # Envelope validation belongs to the response consumer.
            arguments = function.get('arguments')
            if arguments == '' and function.get('name') in {'list_files', 'get_diff'}:
                function['arguments'] = '{}'
                continue  # Match the controller's existing read-only default.
            try:
                decoded = json.loads(arguments, parse_constant=_non_json_constant) if isinstance(arguments, str) else None
            except (ValueError, RecursionError):
                decoded = None
            if not isinstance(decoded, dict):
                function['arguments'] = json.dumps({'_cheapos_invalid_arguments': arguments if isinstance(arguments, str) else json.dumps(arguments),
                                                        '_original_type': type(arguments).__name__})
    return result
