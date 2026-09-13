"""Verification identity: hashes only, never environment values or file contents."""
import hashlib
import json
from pathlib import Path
from .test_profiles import executable_identity
from .workspace import Workspace, git
from .project_permissions import config_identity


def runner_identity(argv, workspace):
    executable = executable_identity(argv[0], workspace) if argv else None
    if not executable:
        return None
    path = Path(executable)
    stat = path.stat()
    environment = path.parent.parent
    config = environment / 'pyvenv.cfg'
    # Site package metadata changes on installation/removal. Include file stats
    # too, so an in-place package edit invalidates previous verification.
    packages = []
    for base in (environment / 'lib', environment / 'Lib'):
        if base.is_dir():
            for site in sorted(base.glob('python*/site-packages')) + list(base.glob('site-packages')):
                for entry in sorted(site.rglob('*')):
                    if '__pycache__' in entry.parts or entry.suffix == '.pyc':
                        continue
                    info = entry.lstat()
                    packages.append([str(entry.relative_to(environment)), info.st_size, info.st_mtime_ns, info.st_ino])
                    if len(packages) > 100000:
                        return None
    return {'executable': executable, 'resolved': str(path.resolve()),
            'stat': [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns],
            'venv': hashlib.sha256(config.read_bytes()).hexdigest() if config.is_file() else None,
            'packages': hashlib.sha256(json.dumps(packages).encode()).hexdigest()}


def evidence_identity(task):
    try:
        workspace = Workspace(task['workspace'])
        runner = runner_identity(task['check_command'], workspace.root)
        if runner is None:
            return None
        value = {'version': 1, 'workspace': str(workspace.root),
                 'generation': task.get('workspace_generation', 0),
                 'baseline': git(workspace.root, 'rev-parse', 'HEAD').strip(),
                 'patch': hashlib.sha256(workspace.patch(validate="branch_run" in task).encode()).hexdigest(),
                 'command': task['check_command'], 'runner': runner,
                 'config': config_identity(workspace.root)}
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    except (OSError, ValueError, KeyError):
        return None


def matches(task, record, identity=None):
    saved = record.get('verification_identity')
    return bool(saved) and saved == (identity if identity is not None else evidence_identity(task))
