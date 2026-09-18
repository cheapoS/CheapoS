"""Bounded task-local edit receipts and version-checked undo, without Git resets."""
import ast
import hashlib
import json
import stat
import uuid

KEEP_EDITS = 16
TEXT_EDITS = frozenset({'write_file', 'replace_text', 'replace_lines', 'append_text'})
MUTATIONS = TEXT_EDITS | {'delete_file', 'apply_merge_version', 'undo_edit'}


def scope(task):
    run = task.get('branch_run') or {}
    return [task.get('workspace'), task.get('workspace_generation', 0),
            run.get('current_item_id'), run.get('expected_feature_tip'),
            (task.get('commits') or [{}])[-1].get('commit')]


def snapshot(workspace, path):
    target = workspace.path(path)
    if not target.exists():
        return None
    data = workspace.text_bytes(path)
    return {'text': data.decode('utf-8'), 'hash': hashlib.sha256(data).hexdigest(),
            'mode': stat.S_IMODE(target.stat().st_mode)}


def identity(value):
    return (value['hash'], value['mode']) if value is not None else None


def syntax_error(path, text, diagnosis=None):
    try:
        if path.endswith('.py'):
            ast.parse(text)
        elif path.endswith('.json'):
            json.loads(text)
    except (SyntaxError, ValueError) as error:
        if diagnosis is not None:
            diagnosis.update(syntax=('tabs' if isinstance(error, TabError) else 'indentation' if isinstance(error, IndentationError) else 'syntax' if isinstance(error, SyntaxError) else 'json'))
            for key, attr in (('line','lineno'), ('column','offset' if isinstance(error,SyntaxError) else 'colno')):
                value = getattr(error,attr,None)
                if type(value) is int: diagnosis[key]=value
        return str(error)
    if diagnosis is not None: diagnosis["syntax"] = "valid" if path.endswith((".py", ".json")) else "unknown"
    return None


def symbols(text):
    result = {}
    def visit(node, parent=''):
        for child in ast.iter_child_nodes(node):
            definition = isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            qualified = parent + child.name if definition else parent
            if definition:
                result.setdefault(qualified, []).append(child.lineno)
            visit(child, qualified + '.' if definition else parent)
    visit(ast.parse(text))
    return result


def structure(before, after, path):
    if not path.endswith('.py'):
        return {}
    try:
        old, new = symbols(before or ''), symbols(after or '')
    except (SyntaxError, ValueError, RecursionError):
        return {}
    removed, added = sorted(old.keys() - new.keys()), sorted(new.keys() - old.keys())
    moved = [{'from': name, 'to': dest, 'line': new[dest][0]}
             for name in removed for dest in added
             if name.rsplit('.', 1)[-1] == dest.rsplit('.', 1)[-1]]
    duplicates = [{'symbol': name, 'lines': lines[:8]} for name, lines in new.items()
                  if len(lines) > max(1, len(old.get(name, [])))]
    if not (removed or added or duplicates):
        return {}
    return {'removed': removed[:16], 'added': [{'symbol': n, 'line': new[n][0]} for n in added[:16]],
            'possible_moves': moved[:16], 'new_duplicates': duplicates[:16],
            'partial': max(len(removed), len(added), len(moved), len(duplicates)) > 16,
            'guidance': 'These are actual Python scopes, not a syntax failure. Check that methods still belong to the intended class and tests to the class with their fixtures. Intentional moves are allowed.'}


def restore(workspace, path, before):
    target = workspace.path(path)
    if before is None:
        target.unlink()
    else:
        target.write_bytes(before['text'].encode('utf-8'))
        target.chmod(before['mode'])


def apply(task, workspace, name, args, operation):
    """Capture only completed text edits; receipts persist with the tool event."""
    path = workspace.path(args['path']).relative_to(workspace.root).as_posix()
    before = snapshot(workspace, path)
    from .edit_recovery import repeated_syntax_edit, syntax_records, syntax_rejection
    if repeated_syntax_edit(task, name, args, path, before):
        return syntax_rejection(task, workspace, name, args, path, before,
                                syntax_records(task)[path]['warning'], replayed=True)
    result = operation(**args)
    after = snapshot(workspace, path)
    if identity(before) == identity(after):
        return {**result, 'changed': False}
    # A valid existing file need not become the starting point for a syntax
    # repair loop. New/chunked files and already-invalid files remain editable.
    diagnosis = {}
    warning = syntax_error(path, after['text'], diagnosis)
    from .structural_telemetry import validation
    try:
        validation(task, before['text'] if before else None, after['text'], diagnosis)
    except Exception:
        pass
    if before is not None and warning and not syntax_error(path, before['text']):
        restore(workspace, path, before)
        return syntax_rejection(task, workspace, name, args, path, before, warning)
    receipt = {'id': uuid.uuid4().hex, 'path': path, 'tool': name, 'scope': scope(task),
               'before': before, 'after': {'hash': after['hash'], 'mode': after['mode']},
               'structure': structure(before['text'] if before else '', after['text'], path)}
    history = task.setdefault('edit_history', [])
    history.append(receipt)
    del history[:-KEEP_EDITS]
    return {**result, 'changed': True, 'edit_id': receipt['id'], 'structure_changes': receipt['structure'],
            'guidance': 'Edit saved. Check structural changes before continuing. If this edit was a mistake, undo_edit(path, edit_id) restores only this file when its version still matches. Use current lines for further edits; verify and submit checkpoint when complete.'}


def undo(task, workspace, path, edit_id):
    path = workspace.path(path).relative_to(workspace.root).as_posix()
    record = next((r for r in task.get('edit_history', []) if r['id'] == edit_id and r['path'] == path), None)
    if not record or record.get('undone') or record['scope'] != scope(task):
        raise ValueError('This edit is not undoable in the current task/item. Read edit history for available receipts.')
    latest = next((r for r in reversed(task['edit_history']) if r['path'] == path and not r.get('undone')), None)
    if latest is not record or identity(snapshot(workspace, path)) != identity(record['after']):
        raise ValueError('Newer changes exist in this file. No undo was applied; inspect current lines and edit history. Other work will not be overwritten.')
    restore(workspace, path, record['before'])
    record['undone'] = True
    return {'path': path, 'updated': True, 'undone_edit_id': edit_id,
            'guidance': 'Restored this file to immediately before that edit. Other files are unchanged. Continue with a corrected edit; verification and independent review still apply.'}


def recent(task, workspace, path=None):
    if path is not None:
        path = workspace.path(path).relative_to(workspace.root).as_posix()
    rows, seen, versions = [], set(), {}
    for record in reversed(task.get('edit_history', [])):
        if path is not None and record['path'] != path:
            continue
        if record['scope'] != scope(task) or record.get('undone'):
            continue
        if record['path'] not in versions:
            try:
                versions[record['path']] = identity(snapshot(workspace, record['path']))
            except (ValueError, OSError, UnicodeError):
                versions[record['path']] = None
        current = versions[record['path']]
        available = record['path'] not in seen and current == identity(record['after'])
        seen.add(record['path'])
        rows.append({'edit_id': record['id'], 'path': record['path'], 'tool': record['tool'],
                     'undo_available': available, 'structure_changes': record['structure'],
                     'current_version_matches': current == identity(record['after'])})
    return {'edits': rows, 'retention': 'Latest 16 completed text edits in this task; undo requires the latest unchanged edit for its file and current item/baseline.'}
