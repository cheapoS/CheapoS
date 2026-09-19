"""Executable checks carry an explicit task-relative working directory."""
import re
import shlex
from pathlib import PurePosixPath


def directory(value='.'):
    if (not isinstance(value, str) or not value or len(value) > 4000
            or any(ord(c) < 32 for c in value) or '\\' in value
            or PurePosixPath(value).is_absolute() or re.match(r'^[A-Za-z]:', value)
            or any(p in {'..', '.git'} for p in PurePosixPath(value).parts)):
        raise ValueError('Check directory must be a relative path inside the task copy, outside Git internals')
    return str(PurePosixPath(value))


def specifications(values):
    from .verification import normalize_unittest
    if not isinstance(values, list) or len(values) > 20:
        raise ValueError('Required checks must be a finite list')
    result = []
    for value in values:
        if isinstance(value, dict) and (set(value) - {'command', 'directory'} or 'command' not in value):
            raise ValueError('Check specifications accept only command and directory')
        command = value.get('command') if isinstance(value, dict) else value
        argv = shlex.split(command) if isinstance(command, str) else command
        if not isinstance(argv, list) or not argv or not all(isinstance(s, str) and s and '\0' not in s for s in argv):
            raise ValueError('Invalid required check command')
        spec = {'command': normalize_unittest(argv), 'directory': directory(value.get('directory', '.') if isinstance(value, dict) else '.')}
        if spec in result:
            raise ValueError('Duplicate required check command and directory')
        result.append(spec)
    return result


def cwd(task, value=None, *, allow_missing=False):
    from .task_commands import directory as resolve
    value = directory(task.get('check_directory', '.') if value is None else value)
    if allow_missing:
        from pathlib import Path
        root = Path(task['workspace']).resolve(strict=True)
        target = (root / value).resolve()
        if not target.is_relative_to(root) or '.git' in target.relative_to(root).parts:
            raise ValueError('Check directory must stay inside the task copy, outside Git internals')
        if target.exists() and not target.is_dir():
            raise ValueError('Check directory is not a directory')
        return target
    return resolve(task['workspace'], value)


def same(record, expected):
    return record.get('command') == expected['command'] and record.get('directory', '.') == expected.get('directory', '.')


def selected_directory(task, argv, requested=None):
    """Use explicit cwd or an unambiguous saved check, never prose inference."""
    if requested is not None:
        return directory(requested)
    run = task.get('branch_run') or {}
    item = next((i for i in run.get('items', []) if i['id'] == run.get('current_item_id')), {})
    specs = run.get('plan', {}).get('final_checks', []) if run.get('status') == 'finalizing' else item.get('required_checks', [])
    matches = {s['directory'] for s in specifications(specs) if s['command'] == argv}
    if len(matches) > 1:
        raise ValueError('This command has checks in multiple directories. Supply the planned directory explicitly.')
    if matches:
        return matches.pop()
    return directory(task.get('check_directory', '.') if argv == task.get('check_command') else '.')
