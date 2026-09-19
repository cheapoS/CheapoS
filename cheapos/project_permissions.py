"""Ephemeral project test grants, bound to controller-registered task copies."""
import hashlib
import json
import uuid
from pathlib import Path
from .test_profiles import executable_identity, match_unittest

CONFIG_FILES = ('pyproject.toml', 'setup.cfg', 'tox.ini', 'unittest.cfg', '.python-version', 'sitecustomize.py', 'usercustomize.py', 'pyvenv.cfg', 'requirements.txt', 'requirements-dev.txt', 'poetry.lock', 'uv.lock', 'Pipfile.lock', 'package.json', 'package-lock.json')


def identity(path):
    path = Path(path).resolve(strict=True)
    stat = path.stat()
    git_path = path / '.git'
    git_stat = git_path.stat()
    marker = hashlib.sha256(git_path.read_bytes()).hexdigest() if git_path.is_file() else None
    return [str(path), stat.st_dev, stat.st_ino, git_stat.st_dev, git_stat.st_ino, marker]


def config_identity(path):
    result = {}
    for name in CONFIG_FILES:
        file = Path(path) / name
        result[name] = hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None
    return result


class ProjectTestGrants:
    def __init__(self, store):
        self.store = store
        self.workspaces = {}
        self.grants = {}
        self.revisions = {}
        for task in store.list(fields=('id', 'workspace', 'source', 'snapshot')):
            self.register(task)

    def register(self, task):
        """Only known snapshot/reconciliation destinations can become eligible."""
        try:
            workspace = Path(task['workspace']).resolve(strict=True)
            directory = self.store.root / 'tasks' / task['id']
            relative = workspace.relative_to(directory).parts
            if relative != ('workspace',) and not (len(relative) == 3 and relative[0] == 'reconciliations' and relative[2] == 'workspace'):
                return
            if task.get('snapshot', {}).get('source') != task['source']:
                return
            self.workspaces[task['id']] = {'source': identity(task['source']), 'workspace': identity(workspace)}
        except (OSError, ValueError, KeyError):
            return

    def binding(self, task):
        registered = self.workspaces.get(task['id'])
        if not registered or registered != {'source': identity(task['source']), 'workspace': identity(task['workspace'])}:
            raise ValueError('Project or task copy changed; authorize this command separately')
        return registered

    def fingerprint(self, task, profile):
        binding = self.binding(task)
        exe = Path(profile['executable']).stat()
        value = {'source': binding['source'], 'executable': [profile['executable'], exe.st_dev, exe.st_ino, exe.st_size, exe.st_mtime_ns],
                 'source_config': config_identity(task['source']), 'workspace_config': config_identity(task['workspace']),
                 'roots': profile['roots'], 'runner': profile['runner'],
                 'venv': config_identity(Path(profile['executable']).parent.parent)}
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    def proposal(self, task, argv):
        try:
            self.binding(task)
            executable = executable_identity(argv[0], task['workspace'])
            args = list(argv[1:]);args = args[1:] if args[:1] == ['-B'] else args
            if args[:2] != ['-m', 'unittest']:
                return None
            args = args[2:]
            root = '.'
            if '-s' in args and args.index('-s')+1 < len(args):
                root = str(Path(args[args.index('-s')+1]))
                if Path(root).is_absolute():
                    root = str(Path(root).resolve().relative_to(Path(task['workspace']).resolve()))
            elif args and 'discover' not in args:
                selectors = [a for a in args if not a.startswith('-')]
                if selectors and all(a.startswith(('tests.', 'tests/')) for a in selectors):
                    root = 'tests'
            profile = {'schema_version':1,'runner':'unittest','project':task['source'],'executable':executable,'roots':[root],'revision':self.revisions.get(task['source'],0)}
            if not match_unittest(argv, task['workspace'], profile)['matched']:
                return None
            profile['fingerprint'] = self.fingerprint(task, profile)
            return profile
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            return None

    def authorize(self, task, argv):
        reason = 'No project-session test grant covers this command'
        for grant in self.grants.values():
            profile = grant['profile']
            if profile['project'] != task['source']:
                continue
            try:
                if self.fingerprint(task, profile) != profile['fingerprint']:
                    reason = 'Runner configuration or executable changed; a new approval is required'
                    continue
            except (OSError, ValueError):
                reason = 'Project or task copy changed; a new approval is required'
                continue
            result = match_unittest(argv, task['workspace'], profile)
            if result['matched']:
                return grant['id'], None
            reason = result['reason']
        return None, reason

    def approve(self, task, pending):
        profile = pending.get('profile')
        if not profile:
            raise ValueError('This command has no eligible project test profile')
        current = self.proposal(task, pending['command'])
        if current != profile or pending['directory'] != task['workspace']:
            raise ValueError('Test profile changed. Request fresh command approval')
        grant = {'id':uuid.uuid4().hex, 'profile':profile, 'expires':'server_restart'}
        self.grants[grant['id']] = grant
        return grant

    def visible(self, task):
        result = []
        for grant in self.grants.values():
            if grant['profile']['project'] != task['source']:
                continue
            try:
                if self.fingerprint(task, grant['profile']) == grant['profile']['fingerprint']:
                    result.append(grant)
            except (OSError, ValueError):
                pass
        return result

    def revoke(self, task, grant_id):
        grant = self.grants.get(grant_id)
        if not grant or grant['profile']['project'] != task['source']:
            raise ValueError('Project test grant not found; refresh permissions')
        del self.grants[grant_id]
        self.revisions[task['source']] = self.revisions.get(task['source'],0)+1
