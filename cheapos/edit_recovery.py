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


def check_feedback(result):
    """Worker-only view: preserve diagnostics and the authoritative stored check."""
    text = ANSI.sub('', result['output'])
    lines = text.splitlines(keepends=True)
    omitted = sum(bool(PASS.fullmatch(line.rstrip('\r\n'))) for line in lines)
    output = ''.join(line for line in lines if not PASS.fullmatch(line.rstrip('\r\n')))
    return {**result, 'output': output,
            'output_representation': 'failure-focused; passing rows omitted' if omitted else 'original diagnostics',
            'omitted_passing_rows': omitted,
            'next_action': 'Inspect the failing assertions and affected code below. Repair only the established defect; a test assumption may need correction if behavior intentionally changed. Do not remove assertions just to pass. Use read_check_output with this run_id for the retained original output.'}
