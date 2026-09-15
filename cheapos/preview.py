"""Operator-launched local previews, separate from task workspaces and profiles."""
import atexit
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import tempfile
import threading
from urllib.parse import urlsplit


def config(values):
    if not isinstance(values, dict):
        raise ValueError('Preview settings must be an object')
    result = {k: str(values.get(k, '')).strip() for k in ('command', 'setup', 'directory', 'url', 'environment', 'checklist')}
    if any(len(v) > 12000 for v in result.values()):
        raise ValueError('Preview setting is too long')
    directory = Path(result['directory'] or '.')
    if directory.is_absolute() or '..' in directory.parts:
        raise ValueError('Working directory must be inside the preview copy')
    for key in ('command', 'setup'):
        if result[key]:
            shlex.split(result[key])
    if result['url']:
        url = urlsplit(result['url'])
        if url.scheme != 'http' or url.hostname not in ('localhost', '127.0.0.1', '::1') or url.username or url.password:
            raise ValueError('Use a local http:// preview URL')
        try:
            if not url.port:
                raise ValueError()
        except ValueError:
            raise ValueError('Include a valid preview port')
    for line in result['environment'].splitlines():
        if line and ('=' not in line or not line.split('=', 1)[0].isidentifier()):
            raise ValueError('Environment uses one NAME=value per line')
    return result


class Previews:
    def __init__(self, engine):
        self.engine = engine
        self.lock = threading.RLock()
        self.runs = {}
        self.file = engine.store.root / 'preview-settings.json'
        atexit.register(self.shutdown)

    def settings(self, values):
        source = str(Path(values.get('repository', '')).expanduser().resolve())
        if source not in {p['path'] for p in self.engine.projects(include_hidden=True)}:
            raise ValueError('Choose a registered project')
        with self.lock:
            try:
                saved = json.loads(self.file.read_text())
            except (OSError, ValueError):
                saved = {}
            if 'config' in values:
                saved[source] = config(values['config'])
                temporary = self.file.with_suffix('.tmp')
                temporary.write_text(json.dumps(saved))
                temporary.chmod(0o600)
                temporary.replace(self.file)
            suggestion = {}
            if (Path(source) / 'cheapos').is_dir() and (Path(source) / 'run.py').is_file():
                suggestion = {'command': 'python3 -B run.py --no-open --port 5174 --data-dir {profile}', 'url': 'http://127.0.0.1:5174'}
            return config(saved.get(source, suggestion))

    def action(self, task_id, action, values):
        task = self.engine.store.get(task_id)
        with self.lock:
            run = self.runs.get(task_id)
            if action == 'preview-start':
                if run and run['thread'].is_alive():
                    raise ValueError('Stop the existing preview first')
                if task.get('trashed_at') or task.get('archived_at'):
                    raise ValueError('Restore this task before launching its preview')
                cfg = config(values['config'] if 'config' in values else self.settings({'repository': task['source']}))
                if not cfg['command']:
                    raise ValueError('Set a preview start command first')
                workspace = task['workspace']
                tip = subprocess.check_output(['git', '-C', workspace, 'rev-parse', 'HEAD'], text=True).strip()
                if values.get('expected_tip') != tip:
                    raise ValueError('The reviewed revision changed. Refresh the review before launching a preview')
                dirty = subprocess.check_output(['git', '-C', workspace, 'status', '--porcelain'], text=True)
                if dirty:
                    raise ValueError('Commit the task changes before previewing so the preview matches a saved revision')
                if cfg['url']:
                    url = urlsplit(cfg['url'])
                    probe = socket.socket(socket.AF_INET6 if ':' in url.hostname else socket.AF_INET)
                    try:
                        probe.bind((url.hostname, url.port))
                    except OSError:
                        raise ValueError('Preview port is in use; stop that preview or choose another port')
                    finally:
                        probe.close()
                root = Path(tempfile.mkdtemp(prefix='cheapos-preview-'))
                run = dict(status='starting', tip=tip, branch=task.get('branch_run', {}).get('feature_ref', 'task copy'),
                           root=str(root), url=cfg['url'], logs='', process=None, stop=threading.Event(), config=cfg)
                run['thread'] = threading.Thread(target=self.launch, args=(run, workspace), daemon=True)
                self.runs[task_id] = run
                run['thread'].start()
            elif action == 'preview-stop':
                if run:
                    self.stop(run)
            elif action != 'preview-status':
                raise ValueError('Unknown preview action')
            if not run:
                return {'status': 'stopped', 'logs': '', 'config': self.settings({'repository': task['source']})}
            try:
                current = subprocess.check_output(['git', '-C', task['workspace'], 'rev-parse', 'HEAD'], text=True).strip()
                dirty = subprocess.check_output(['git', '-C', task['workspace'], 'status', '--porcelain'], text=True)
            except (OSError, subprocess.CalledProcessError):
                current, dirty = '', ''
            return {k: run[k] for k in ('status', 'tip', 'branch', 'root', 'url', 'logs', 'config')} | {'outdated': current != run['tip'] or bool(dirty)}

    def execute(self, run, args, cwd, env):
        if run['stop'].is_set():
            return False
        process = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        run['process'] = process
        if run['stop'].is_set():
            self.stop(run)
        while True:
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk:
                break
            run['logs'] = (run['logs'] + chunk.decode('utf-8', errors='replace'))[-64000:]
        return process.wait() == 0 and not run['stop'].is_set()

    def launch(self, run, workspace):
        try:
            root = Path(run['root'])
            copy = root / 'workspace'
            profile = root / 'profile'
            profile.mkdir()
            env = os.environ.copy()
            if not self.execute(run, ['git', 'clone', '--no-hardlinks', '--no-checkout', '--', workspace, str(copy)], root, env):
                return
            if not self.execute(run, ['git', 'checkout', '--detach', run['tip']], copy, env):
                return
            cfg = run['config']
            cwd = (copy / (cfg['directory'] or '.')).resolve()
            if not cwd.is_relative_to(copy.resolve()) or not cwd.is_dir():
                raise ValueError('Preview working directory is missing or outside the copy')
            expand = lambda value: value.replace('{profile}', str(profile)).replace('{port}', str(urlsplit(cfg['url']).port or ''))
            for line in cfg['environment'].splitlines():
                if line:
                    key, value = line.split('=', 1)
                    env[key] = expand(value)
            if cfg['setup']:
                run['status'] = 'setting_up'
                if not self.execute(run, [expand(a) for a in shlex.split(cfg['setup'])], cwd, env):
                    return
            run['status'] = 'running'
            self.execute(run, [expand(a) for a in shlex.split(cfg['command'])], cwd, env)
        except Exception as error:
            run['logs'] = (run['logs'] + '\n' + str(error))[-64000:]
        finally:
            run['status'] = 'stopped' if run['stop'].is_set() else 'exited'

    def stop(self, run):
        run['stop'].set()
        process = run.get('process')
        if process:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            def kill_later():
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            threading.Thread(target=kill_later, daemon=True).start()
        run['status'] = 'stopping' if run['thread'].is_alive() else 'stopped'

    def shutdown(self):
        for run in list(self.runs.values()):
            self.stop(run)
            process = run.get('process')
            if process:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            thread = run.get('thread')
            if thread and thread is not threading.current_thread():
                thread.join(timeout=2)
