"""Actionable repair feedback; original checks and file authority stay intact."""
import hashlib
import ast
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


def constraint_feedback(task, workspace, args, error):
    from .edit_history import scope
    path = workspace.path(args['path']).relative_to(workspace.root).as_posix()
    run = task.get('branch_run') or {}
    item = next((i for i in run.get('items', []) if i['id'] == run.get('current_item_id')), {})
    repair = item.get('review_repair') or {}
    identity = [*scope(task), repair.get('candidate_id'),
                (task.get('providers', {}).get('worker') or {}).get('model')]
    records = task.setdefault('edit_constraint_recovery', {})
    # Another implementation path cannot hide the same missing reproduction.
    key = error.code if error.code == 'repair_evidence_required' else error.code + ':' + path
    previous = records.get(key, {})
    attempts = previous.get('attempts', 0) + 1 if previous.get('scope') == identity else 1
    records[key] = {'scope': identity, 'attempts': attempts}
    result = {'code': error.code, 'error': str(error), 'path': path, 'attempts': attempts,
              'executed': False, 'changed': False, 'updated': False, **error.details}
    if error.code == 'repair_evidence_required':
        from .branch_disagreement import reproduction_context
        result['reproduction'] = reproduction_context(task, workspace)
        result['guidance'] = ('Implementation editing is waiting for reproduction evidence. Use the supplied planned checks and test-file evidence; '
            'if no test file was identified, locate those checks\' test definitions with the normal read tools. '
            'Add one small regression for the specific reviewer claim, preserve existing assertions, and run the planned check through run_checks. '
            'An existing test file needs a small edit, not write_file. Place tests in a discoverable test class/function, not below or inside an entry-point block. '
            'A passing check may mean the new test did not run: inspect its discovered test names. '
            'Do not repeat implementation edits until a current failing test is recorded. '
            'If a focused test disproves the claim, submit that counterevidence at checkpoint. Independent review remains required.')
    elif error.code == 'file_already_exists':
        result['guidance'] = ('This file already exists and was preserved. Use the current numbered lines for a small replace_lines edit, '
            'or read the relevant later range first. Do not retry write_file or delete the file to replace it. Preserve existing tests and unaffected functions.')
    else:
        result['guidance'] = ('The oversized edit was not executed. The supplied edit_size identifies each exceeded limit; a chunk can fit the line limit and still exceed the UTF-8 byte limit. '
            'Use one complete method or a few adjacent assertions against current lines, preserving indentation and literal newlines. '
            'Do not repeat the whole-file replacement or truncate the intended code. Add remaining changes in later turns, then verify and submit for independent review.')
    return result


def syntax_records(task, key='syntax_edit_recovery'):
    """Saved within the current work item; Resume does not renew attempts."""
    run = task.get('branch_run') or {}
    scope = [task.get('workspace'), task.get('workspace_generation', 0),
             run.get('current_item_id'), len(task.get('requests') or [task.get('prompt')])]
    state = task.setdefault(key, {'scope': scope, 'files': {}})
    if state['scope'] != scope:
        state.update(scope=scope, files={})
    return state['files']


def allow_exact_text(task):
    if (task.get('text_edit_recovery') and any(r.get('attempts', 0) >= 2
            for r in syntax_records(task, 'text_edit_recovery').values())):
        return False  # The syntax escape hatch must not keep offering a failed strategy.
    return bool(task.get('syntax_edit_recovery') and
                any(r.get('attempts', 0) >= 2 for r in syntax_records(task).values()))


def text_rejection(task, workspace, args, path, before, matches):
    records = syntax_records(task, 'text_edit_recovery')
    prior = records.get(path, {})
    attempts = prior.get('attempts', 0) + 1 if prior.get('hash') == before['hash'] else 1
    records[path] = {'hash': before['hash'], 'attempts': attempts, 'matches': matches,
                     'fingerprint': syntax_fingerprint('replace_text', args, path)}
    description = 'was not found' if matches == 0 else f'matched {matches} times'
    return {'path': path, 'code': 'text_edit_rejected', 'updated': False, 'changed': False,
            'rejected': True, 'executed': False, 'matches': matches, 'attempts': attempts,
            'hash': before['hash'], 'error': f"old_text {description} in '{path}'. No edit was made.",
            'current_file': workspace.read_file(path, 1, 100),
            'guidance': 'The exact replacement is invalid for this file version. Do not repeat it or append a claimed fix. '
                        'Use the current numbered lines for replace_lines, or inspect a relevant later range. '
                        'The intended change may already exist; check the remaining requirements before editing.'}


def syntax_fingerprint(name, args, path):
    return hashlib.sha256(json.dumps([name, {**args, 'path': path, 'expected_hash': None}],
                                     sort_keys=True).encode()).hexdigest()


def repeated_syntax_edit(task, name, args, path, before):
    prior = syntax_records(task).get(path, {})
    return bool(before and prior.get('hash') == before['hash'] and
                prior.get('fingerprint') == syntax_fingerprint(name, args, path))


def syntax_rejection(task, workspace, name, args, path, before, warning, replayed=False):
    records = syntax_records(task)
    prior = records.get(path, {})
    # Appending comments or changing whitespace cannot renew the same failed
    # Python repair. An actual code change starts a new repair evidence state.
    text = before['text']
    semantic = ast.dump(ast.parse(text), include_attributes=False) if path.endswith('.py') else text
    version = hashlib.sha256(semantic.encode()).hexdigest()
    attempts = prior.get('attempts', 0) + 1 if prior.get('version') == version else 1
    records[path] = {'hash': before['hash'], 'version': version, 'attempts': attempts,
                     'fingerprint': syntax_fingerprint(name, args, path), 'warning': warning}
    line = args.get('start_line')
    if line is None:
        offset = text.find(args.get('old_text', '')) if name == 'replace_text' else len(text)
        line = text.count('\n', 0, max(0, offset)) + 1
    start = max(1, line - 5)
    return {'path': path, 'updated': False, 'changed': False, 'rejected': True,
            'code': 'syntax_edit_rejected', 'rolled_back': not replayed, 'executed': not replayed,
            'syntax_warning': warning, 'hash': before['hash'], 'attempts': attempts,
            'guidance': ('This exact edit already broke syntax on this file version; it was not executed again. '
                         if replayed else 'This edit broke syntax, so cheapoS restored the exact pre-edit file. ')
                        + 'Other edits remain saved. Preserve indentation and literal newlines in replacement text. '
                          'Use the current file, not the rejected version; choose a different repair.',
            'current_file': workspace.read_file(path, start, start + 79)}


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
