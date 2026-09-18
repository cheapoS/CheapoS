"""Local, bounded structural metadata. Never retains source or exception text."""
import re

VERSION = 1
LIMIT = 24
BOUNDARIES = {'request_wire', 'response_extraction', 'fallback_decode', 'argument_decode', 'edit_validation'}
ENUMS = {'extraction': {'native', 'xml', 'json_fallback', 'none'},
         'syntax': {'valid', 'syntax', 'indentation', 'tabs', 'json', 'unknown'},
         'upstream': {'unknown'}}
NUMBERS = {'wire_bytes', 'argument_bytes', 'text_bytes', 'lines', 'leading_spaces',
           'leading_tabs', 'before_text_bytes', 'before_lines', 'before_leading_spaces', 'before_leading_tabs', 'before_bytes', 'after_bytes', 'line', 'column', 'tool_count'}


def text_metrics(text):
    lines = text.splitlines()
    spaces = tabs = 0
    for line in lines:
        leading = line[:len(line)-len(line.lstrip(' \t'))]
        spaces += leading.count(' '); tabs += leading.count('\t')
    return {'text_bytes':len(text.encode('utf-8')), 'lines':len(lines),
            'leading_spaces':spaces, 'leading_tabs':tabs}


def safe(rows):
    result = []
    if not isinstance(rows, list): return result
    for row in rows[-LIMIT:]:
        if not isinstance(row, dict) or row.get('boundary') not in BOUNDARIES: continue
        clean = {'version':VERSION, 'boundary':row['boundary'], 'upstream':'unknown'}
        for key, value in row.items():
            if key in NUMBERS and type(value) is int and 0 <= value <= 2**53: clean[key] = value
            elif key in ENUMS and isinstance(value,str) and value in ENUMS[key]: clean[key] = value
            elif key == 'transformed' and type(value) is bool: clean[key] = value
            elif key == 'tool_id' and isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,80}',value): clean[key]=value
        result.append(clean)
    return result


def add(record, boundary, **fields):
    # Diagnostics must never become a new execution/recovery prerequisite.
    try:
        rows = record.get('structural_telemetry', [])
        record['structural_telemetry'] = safe([*rows, {'boundary':boundary, **fields}])
    except Exception:
        pass


def task_record(task):
    return (task.get('request_metrics') or [{}])[-1]


def arguments(task, call, params):
    try:
        text = '\n'.join(v for k,v in params.items() if k in {'content','text','old_text','new_text'} and isinstance(v,str))
        add(task_record(task), 'argument_decode', tool_id=call['id'],
            argument_bytes=len(call['function']['arguments'].encode('utf-8')),
            transformed=True, **text_metrics(text))
        publish(task)
    except Exception:
        pass


def validation(task, before, after, diagnosis):
    try:
        record = task_record(task)
        tool_id = next((r.get('tool_id') for r in reversed(record.get('structural_telemetry',[])) if r.get('boundary')=='argument_decode'), None)
        add(record, 'edit_validation', tool_id=tool_id, before_bytes=len((before or '').encode('utf-8')),
            after_bytes=len(after.encode('utf-8')), transformed=before != after,
            **{'before_'+k:v for k,v in text_metrics(before or '').items()},
            **text_metrics(after), **diagnosis)
        publish(task)
    except Exception:
        pass


def publish(task):
    try:
        from .routing_trace import request
        request(task, task_record(task))
    except Exception:
        pass
