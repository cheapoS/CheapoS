"""Verification identity: hashes only, never environment values or file contents."""
import hashlib
import json
from pathlib import Path
from .test_profiles import executable_identity
from .workspace import Workspace, git
from .project_permissions import config_identity
from .check_output import complete_output


def normalize_unittest(argv):
    """Canonicalize unittest test names, never executable paths/discovery options."""
    argv = list(argv)
    if '-m' not in argv:
        return argv
    module = argv.index('-m') + 1
    if module >= len(argv) or argv[module] != 'unittest' or 'discover' in argv[module + 1:]:
        return argv
    skip = False
    for index in range(module + 1, len(argv)):
        arg = argv[index]
        if skip:
            skip = False
            continue
        if arg == '-k':
            skip = True
        if arg.startswith(('-', '/')):
            continue
        name = arg[2:] if arg.startswith('./') else arg
        if name.endswith('.py'):
            name = name[:-3]
        name = name.replace('.py.', '.').replace('/', '.')
        if all(part.isidentifier() for part in name.split('.')):
            argv[index] = name
    return argv


def reusable_check(task, argv, directory=None):
    """Latest exact successful command only; reread all inputs before reuse."""
    directory = task.get('check_directory', '.') if directory is None else directory
    record = (task.get('checks') or [{}])[-1]
    if (record.get('command') != argv or record.get('directory', '.') != directory or record.get('passed') is not True
            or record.get('exit_code') != 0 or record.get('reason') or not complete_output(record)
            or record.get('outcome', 'passed') != 'passed'
            or not record.get('input_identity')
            or record.get('input_identity') != record.get('verification_identity')):
        return None
    identity = evidence_identity({**task, 'check_command': argv, 'check_directory': directory})
    return record if identity and identity == record['verification_identity'] else None


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
        from .check_specs import cwd
        working = cwd(task)
        from .command_backend import captured, identity as backend_identity, executable
        backend = captured(task)
        isolation = backend_identity(backend, workspace.root, working)
        argv = task['check_command']
        if backend != 'host':
            resolved = executable(argv[0], workspace.root, working)
            if not resolved:
                return None
            argv = [resolved, *argv[1:]]
        runner = runner_identity(argv, working)
        if runner is None:
            return None
        value = {'version': 1, 'workspace': str(workspace.root),
                 'generation': task.get('workspace_generation', 0),
                 'baseline': git(workspace.root, 'rev-parse', 'HEAD').strip(),
                 'patch': hashlib.sha256(workspace.patch(validate="branch_run" in task).encode()).hexdigest(),
                 'command': task['check_command'], 'runner': runner,
                 'config': config_identity(workspace.root)}
        if isolation is not None:
            value['command_backend'] = isolation
        if task.get('check_directory', '.') != '.':
            stat = working.stat()
            value['check_directory'] = [task['check_directory'], str(working), stat.st_dev, stat.st_ino]
            value['directory_config'] = config_identity(working)
        if task.get('command_environment_revision'):
            value['command_environment_revision'] = task['command_environment_revision']
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    except (OSError, ValueError, KeyError):
        return None


def matches(task, record, identity=None):
    saved = record.get('verification_identity')
    return bool(saved) and saved == (identity if identity is not None else evidence_identity(task))
