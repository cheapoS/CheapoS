"""Operator-granted command execution in one task copy, independent of test evidence.

This is a host process permission, not a sandbox. Only trusted controller entry
points may grant it; model arguments and project files cannot create grants.
"""
from pathlib import Path
import hashlib


def identity(path):
    path = Path(path).resolve(strict=True)
    stat = path.stat()
    git = path / ".git"
    marker = None
    if git.exists():
        git_stat = git.stat()
        marker = [git_stat.st_dev, git_stat.st_ino, hashlib.sha256(git.read_bytes()).hexdigest() if git.is_file() else None]
    return [str(path), stat.st_dev, stat.st_ino, marker]


def binding(task):
    root = Path(task['workspace']).resolve(strict=True)
    source = Path(task['source']).resolve(strict=True)
    if root == source or source in root.parents or root in source.parents:
        raise ValueError('Commands require a separate task copy')
    if root.name != 'workspace' or root.parent.name != task['id'] or root.parent.parent.name != 'tasks':
        raise ValueError('Commands require the registered task workspace')
    return {'task_id': task['id'], 'source': identity(source), 'workspace': identity(root)}


def grant(task, enabled):
    if type(enabled) is not bool:
        raise ValueError('Provide an explicit task command permission decision')
    if enabled:
        task['task_command_permission'] = binding(task)
    else:
        task.pop('task_command_permission', None)


def allowed(task):
    try:
        return task.get('task_command_permission') == binding(task)
    except (KeyError, OSError, ValueError):
        return False


def directory(workspace, value):
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError('Use a task-relative working directory, or .')
    root = Path(workspace).resolve(strict=True)
    target = (root / value).resolve(strict=True)
    if not target.is_relative_to(root) or '.git' in Path(value).parts or '.git' in target.relative_to(root).parts:
        raise ValueError('Command directory must stay inside the task copy, outside Git internals')
    if not target.is_dir():
        raise ValueError('Command directory does not exist')
    return target


POLICY = """Use run_command for task-local setup, dependency installation, and diagnostics when task command permission is enabled. Inspect the project's actual files and command output to choose the next step; there is no package-manager recipe catalog. Commands run as direct argument vectors, without shell operators; make separate calls for separate commands. A successful setup command is NOT verification: run_checks and independent checkpoint review are still required. Do not change required checks or package scripts merely to hide missing dependencies. Do not deploy, push, commit, access credentials, or modify other checkouts. Dependency scripts execute with the host user's permissions; the task copy is not a security sandbox."""
