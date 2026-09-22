"""Optional local diagnostics, separate from execution and accounting evidence."""
import copy
import hashlib
import json
import re

TRACE_KEYS = ('routing_traces', 'routing_traces_truncated')


def without_details(task):
    """A shallow projection; never mutate a live task or its request records."""
    result = {key: value for key, value in task.items() if key not in TRACE_KEYS}
    if 'request_metrics' in task:
        result['request_metrics'] = [
            {key: value for key, value in record.items() if key != 'structural_telemetry'}
            for record in task['request_metrics']]
    return result


def extract(task):
    from .structural_telemetry import safe
    details = {key: task[key] for key in TRACE_KEYS if key in task}
    measurements = {record['id']: safe(record['structural_telemetry'])
                    for record in task.get('request_metrics', [])
                    if record.get('id') and record.get('structural_telemetry')}
    if measurements:
        details['request_measurements'] = measurements
    return {'version': 1, **details} if details else None


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def path_for(directory, reference):
    key = reference.get('digest') if isinstance(reference, dict) and reference.get('version') == 1 else None
    if not isinstance(key, str) or not re.fullmatch(r'[0-9a-f]{64}', key):
        raise ValueError('Invalid diagnostic reference')
    directory = directory / 'diagnostics'
    if directory.is_symlink():
        raise ValueError('Diagnostic directory must be task-owned')
    path = directory / (key + '.json')
    if path.is_symlink():
        raise ValueError('Diagnostic file must be task-owned')
    return path


def read(directory, task):
    inline = extract(task)
    reference = task.get('diagnostics_ref')
    if not reference:
        return inline or {'version': 1}, None
    try:
        path = path_for(directory, reference)
        details = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(details, dict) or details.get('version') != 1 or digest(details) != reference['digest']:
            raise ValueError('Diagnostic snapshot does not match its reference')
    except (OSError, ValueError, TypeError):
        return inline or {'version': 1}, 'Some local diagnostics are unavailable. Saved work and accounting are unaffected.'
    if inline:
        details.update(inline)
    return details, None


def restore(directory, task):
    """Hydrate only runtime reads. Startup, polling and summaries stay lean."""
    details, _ = read(directory, task)
    for key in TRACE_KEYS:
        if key in details:
            task[key] = copy.deepcopy(details[key])
    measurements = details.get('request_measurements', {})
    for record in task.get('request_metrics', []):
        if record.get('id') in measurements:
            record['structural_telemetry'] = copy.deepcopy(measurements[record['id']])
    return task


def persist(directory, task, write_json):
    """Write optional immutable data before the task's atomic commit.

    A failed diagnostics write falls back to the previous inline format. It
    cannot block saving work. The existing snapshot remains valid until the
    caller commits the new task reference; cleanup must happen after that.
    """
    details = extract(task)
    if details is None:
        return task
    reference = {'version': 1, 'digest': digest(details),
                 'trace_count': len(details.get('routing_traces', [])),
                 'request_count': len(details.get('request_measurements', {}))}
    try:
        path = path_for(directory, reference)
        if not path.exists():
            write_json(path, details, compact=True)
    except (OSError, ValueError):
        return task
    return {**without_details(task), 'diagnostics_ref': reference}


def cleanup(directory, reference):
    """Reclaim superseded snapshots, never execution records or diagnostic rows."""
    if not reference:
        return
    try:
        current = path_for(directory, reference)
        for path in current.parent.glob('*.json'):
            if path != current and re.fullmatch(r'[0-9a-f]{64}\.json', path.name) and not path.is_symlink():
                path.unlink()
    except (OSError, ValueError):
        pass  # Optional maintenance cannot block execution.


def page(directory, task, offset=0, limit=8):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 32:
        raise ValueError('Invalid diagnostic page')
    details, notice = read(directory, task)
    traces = details.get('routing_traces', [])
    # Display each page chronologically; page zero contains the latest traces.
    end = max(0, len(traces) - offset)
    start = max(0, end - limit)
    return {'task_id': task['id'], 'version': 1, 'routing_traces': traces[start:end],
            'routing_traces_truncated': details.get('routing_traces_truncated', False),
            'total': len(traces), 'offset': offset, 'next_offset': offset + limit if start else None,
            'notice': notice}
