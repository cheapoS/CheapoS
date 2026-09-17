"""Actionable repair feedback; original checks and file authority stay intact."""
import hashlib
import json
import re
from pathlib import PurePosixPath


def fingerprint(args):
    value = {key: args.get(key) for key in ('start_line', 'end_line', 'new_text', 'expected_hash')}
    value['path'] = str(PurePosixPath(args.get('path', '')))
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def rejected(task, args, current, error):
    path = str(PurePosixPath(args.get('path', '')))
    records = task.setdefault('edit_recovery', {})
    prior = records.get(path, {})
    version = current.get('hash')
    attempts = prior.get('attempts', 0) + 1 if version and prior.get('hash') == version else 1
    records[path] = {'hash': version, 'attempts': attempts,
                     'fingerprint': fingerprint({**args, 'expected_hash': version})}
    while len(records) > 128:
        del records[next(iter(records))]
    return {'error': error, 'code': 'invalid_edit_range', 'executed': False,
            'attempted_range': {k: args.get(k) for k in ('start_line', 'end_line')},
            'current_file': current, 'attempts': attempts,
            'guidance': 'Use the supplied current numbered lines to correct the edit. Do not repeat the rejected range or ask the operator for file contents. File versions are tracked automatically.'}


PASS = re.compile(r'^(?:[✔✓] .+|test\S* \([^\n]+\) \.\.\. ok)\s*$')
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
EXCEPTION = re.compile(r'^([\w.]+(?:Error|Exception)(?::[^\n]*)?)$', re.M)


def failure_groups(output):
    """Group identical reported exceptions, without claiming they prove one cause."""
    groups = {}
    for match in EXCEPTION.finditer(ANSI.sub('', output or '')):
        message = match.group(1)
        groups[message] = groups.get(message, 0) + 1
    return [{'message': message, 'occurrences': count} for message, count in groups.items()][:16]


def check_state(task):
    check = (task.get('checks') or [{}])[-1]
    if not check:
        return {'state': 'not_run'}
    same = (check.get('digest') == hashlib.sha256(task.get('patch', '').encode()).hexdigest()
            and check.get('generation', 0) == task.get('workspace_generation', 0))
    return {'state': 'same_candidate' if same else 'predates_current_changes',
            'run_id': check.get('run_id'), 'reported_passed': check.get('passed'),
            'command': check.get('command'), 'failure_groups': failure_groups(check.get('output')),
            'guidance': ('This result describes the current patch; normal command/environment identity validation still applies.' if same else
                         'Files changed after this check (or its identity is missing). These failures do not establish a defect in the current files. Verify the focused repair before repeating it; never claim a pass from old evidence.')}


def repair_packet(task):
    from .edit_history import recent
    from .workspace import Workspace
    edits = recent(task, Workspace(task['workspace']))['edits'][:6] if task.get('edit_history') else []
    return {'latest_check': check_state(task), 'recent_edits': edits,
            'next_action': 'Use actual symbol ownership and current lines. Undo a mistaken edit using an available edit_id, or repair only the established defect. Do not rewrite unrelated functions or weaken assertions. Rerun the approved focused check after fixing the cause, then submit checkpoint.'}


def check_feedback(result):
    """Worker-only view: preserve diagnostics and the authoritative stored check."""
    text = ANSI.sub('', result.get('output') or '')
    lines = text.splitlines(keepends=True)
    omitted = sum(bool(PASS.fullmatch(line.rstrip('\r\n'))) for line in lines)
    output = ''.join(line for line in lines if not PASS.fullmatch(line.rstrip('\r\n')))
    return {**result, 'output': output, 'failure_groups': failure_groups(text),
            'output_representation': 'failure-focused; passing rows omitted' if omitted else 'original diagnostics',
            'omitted_passing_rows': omitted,
            'next_action': 'Inspect the failing assertions and affected code below. Repair only the established defect; a test assumption may need correction if behavior intentionally changed. Do not remove assertions just to pass. Use read_check_output with this run_id for the retained original output.'}
