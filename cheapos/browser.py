"""Task-authorized browser sessions and immutable candidate-bound observations."""
import hashlib
import json
import os
from pathlib import Path
import queue
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from urllib.parse import urljoin, urlsplit

from . import task_commands, work_policy
from .preview import config
from .command_backend import require_host_preview
from .workspace import Workspace, git


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def inputs(directory):
    """Eligible file identities, including uncommitted and untracked inputs."""
    workspace = Workspace(directory)
    names = git(workspace.root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split('\0')
    files = []
    total = 0
    for name in sorted(set(filter(None, names))):
        try:
            path = workspace.path(name)
        except ValueError:
            continue
        if path.is_file():
            data = path.read_bytes()
            if len(data) > 2_000_000:
                raise ValueError('Preview candidate contains an oversized file')
            total += len(data)
            if total > 100_000_000 or len(files) >= 5000:
                raise ValueError('Preview candidate exceeds snapshot resource bounds')
            files.append([name, hashlib.sha256(data).hexdigest(), bool(path.stat().st_mode & 0o111)])
    return files


def candidate(task):
    run = task.get('branch_run') or {}
    return digest({'task': task['id'], 'workspace': task['workspace'],
                   'generation': task.get('workspace_generation', 0), 'files': inputs(task['workspace']),
                   'requests': task.get('requests', []), 'prompt': task.get('prompt'),
                   'plan': run.get('plan'), 'guidance': run.get('guidance', []),
                   'steer_guidance': task.get('steer_guidance')})


class Driver:
    """Bounded RPC with cancellation; all browser processes belong to this group."""
    def __init__(self):
        env = {k: v for k, v in os.environ.items() if k in {'PATH', 'HOME', 'SystemRoot', 'LANG', 'PLAYWRIGHT_BROWSERS_PATH'}}
        self.process = subprocess.Popen([sys.executable, '-u', str(Path(__file__).with_name('browser_driver.py'))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, start_new_session=True, env=env)
        self.replies = queue.Queue()
        self.close_lock = threading.Lock()
        self.closed = False
        def read():
            try:
                for line in self.process.stdout:
                    if len(line) > 300000:
                        self.replies.put({'error': 'Browser response exceeded its bound'})
                        break
                    self.replies.put(json.loads(line))
            except (OSError, ValueError):
                pass
            finally:
                self.replies.put({'error': 'Browser process exited'})
        threading.Thread(target=read, daemon=True).start()

    def call(self, args, guard):
        guard()
        try:
            self.process.stdin.write(json.dumps(args) + '\n')
            self.process.stdin.flush()
        except (OSError, ValueError):
            raise ValueError('Browser process exited; stop and start the preview again') from None
        deadline = time.monotonic() + 20
        try:
            while time.monotonic() < deadline:
                guard()
                try:
                    return self.replies.get(timeout=.05)
                except queue.Empty:
                    continue
            raise ValueError('Browser operation timed out; session stopped')
        except BaseException:
            self.close()
            raise

    def close(self):
        with self.close_lock:
            if self.closed:
                return
            self.closed = True
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.process.wait(timeout=3)
        for pipe in (self.process.stdin, self.process.stdout):
            try: pipe.close()
            except (OSError, ValueError): pass


class Browsers:
    def __init__(self, engine):
        self.engine = engine
        self.sessions = {}
        self.lock = threading.RLock()

    def permission(self, task_id, values):
        """Operator endpoint only. A grant is never created by a model tool."""
        with self.engine.lock:
            runtime = self.engine.runtimes.get(task_id)
            running = bool(runtime and runtime.thread and runtime.thread.is_alive())
            task = runtime.task if running else self.engine.store.get(task_id)
            if not values:
                grant = task.get('browser_permission') or {}
                return {'enabled': bool(grant), 'directory': task['workspace'], 'config': grant.get('config') or self.engine.previews.settings({'repository': task['source']})}
            if type(values.get('enabled')) is not bool:
                raise ValueError('Provide an explicit browser permission decision')
            if values['enabled']:
                require_host_preview(task)
                if values.get('directory') != task['workspace']:
                    raise ValueError('Task copy changed; reopen browser permission before authorizing')
                if running:
                    raise ValueError('Pause the task before changing browser permission')
                cfg = config(values.get('config', {}))
                if not cfg['command'] or not cfg['url']:
                    raise ValueError('Set a start command and local preview URL')
                grant = {'binding': task_commands.binding(task), 'config': cfg}
                task['browser_permission'] = grant
            else:
                task.pop('browser_permission', None)
            self.engine.event(task, 'permission',
                'Agent browser verification authorized' if values['enabled'] else 'Agent browser permission revoked',
                {'enabled': values['enabled'], 'directory': task['workspace']})
            self.engine.store.save(task)
        self.stop(task_id)
        return {'enabled': values['enabled']}

    def authorized(self, task):
        require_host_preview(task)
        grant = task.get('browser_permission') or {}
        if grant.get('binding') != task_commands.binding(task):
            raise ValueError('Authorize agent browser verification in Session permissions or the task preview panel first')
        if work_policy.read_only(task) or task.get('archived_at') or task.get('trashed_at'):
            raise ValueError('Browser execution is unavailable for this task state')
        if task.get('workspace_cleanup', {}).get('state') in {'reclaiming', 'reclaimed'}:
            raise ValueError('Task workspace is unavailable')
        return config(grant['config'])

    def stop(self, task_id):
        with self.lock:
            session = self.sessions.pop(task_id, None)
        if session:
            try:
                if session.get('driver'): session['driver'].close()
            finally:
                self.engine.previews.stop(session['run'])

    def shutdown(self):
        for task_id, session in list(self.sessions.items()):
            self.stop(task_id)
            run = session['run']
            process = run.get('process')
            if process:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
            thread = run.get('thread')
            if thread and thread is not threading.current_thread():
                thread.join(timeout=2)

    def action(self, task, args, runtime):
        action = args.get('action')
        if action == 'stop':
            self.stop(task['id'])
            return {'status': 'stopped'}
        cfg = self.authorized(task)
        guard = runtime.guard if runtime else lambda: None
        guard()
        if action == 'status':
            session = self.sessions.get(task['id'])
            return {'status': session['run']['status'] if session else 'stopped',
                    'candidate': session['candidate'] if session else None,
                    'current_candidate': candidate(task), 'config': cfg,
                    'logs': session['run']['logs'][-8000:] if session else ''}
        try:
            if action == 'open':
                if runtime is None:
                    raise ValueError('Browser actions require an active worker runtime')
                return self.open(task, runtime)
            if action == 'start':
                return self.start(task, cfg, guard)
            session = self.sessions.get(task['id'])
            if not session:
                raise ValueError('Start the authorized browser preview first')
            if session['candidate'] != candidate(task) or session['config'] != cfg:
                raise ValueError('Preview candidate or consent changed; stop and start again')
            if session['run']['status'] != 'running':
                raise ValueError('Preview is not running; inspect status and preview logs')
            if not session.get('driver'):
                raise ValueError('Open the browser after the preview is running')
            self.validate_copy(session)
            request = self.arguments(action, args, cfg)
            evidence_id = uuid.uuid4().hex
            directory = self.directory(task)
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if action == 'screenshot': request['path'] = str(directory / (evidence_id + '.png'))
            result = session['driver'].call(request, guard)
            guard()
            if self.sessions.get(task['id']) is not session:
                raise InterruptedError('Browser session was stopped')
            if session['candidate'] != candidate(task) or session['run']['status'] != 'running':
                raise ValueError('Candidate changed during browser operation; result is not current evidence')
            self.validate_copy(session)
            record = {'id': evidence_id, 'candidate': session['candidate'], 'action': action,
                      'arguments': {k: v for k, v in request.items() if k != 'path'},
                      'result': result, 'config_digest': digest(cfg), 'session': session['id'],
                      'preview': {key: cfg[key] for key in ('command', 'setup', 'directory', 'url')},
                      'created_at': time.time(), 'approved': False,
                      'owner_item_id': (task.get('branch_run') or {}).get('current_item_id')}
            if action == 'screenshot' and not result.get('error'):
                data = Path(request['path']).read_bytes()
                if len(data) > 20 * 1024 * 1024 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise ValueError('Invalid or oversized browser screenshot')
                record['image_digest'] = hashlib.sha256(data).hexdigest()
                record['image'] = 'browser:' + evidence_id
            if result.get('error'):
                record['error'] = result['error']
            self.save(task, record)
            return record
        except BaseException:
            self.stop(task['id'])
            raise

    @staticmethod
    def arguments(action, args, cfg):
        from .browser_driver import origin
        request = {'action': action}
        if action == 'navigate':
            value = args.get('url', '')
            if not isinstance(value, str) or len(value) > 2000:
                raise ValueError('Provide a bounded local URL')
            url = urljoin(cfg['url'], value)
            if origin(url) != origin(cfg['url']):
                raise ValueError('Navigation must stay on the authorized preview origin')
            request['url'] = url
        elif action in {'click', 'fill', 'press', 'select'}:
            selector = args.get('selector')
            if not isinstance(selector, str) or not 0 < len(selector) <= 500:
                raise ValueError('Provide a selector of 1–500 characters')
            request['selector'] = selector
            if action != 'click':
                value = args.get('value')
                if not isinstance(value, str) or len(value) > 4000:
                    raise ValueError('Provide a value of up to 4,000 characters')
                if action == 'press' and value not in {'Enter', 'Tab', 'Escape', 'Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'}:
                    raise ValueError('Unsupported key')
                request['value'] = value
        elif action == 'viewport':
            for key, low, high in [('width', 320, 1920), ('height', 240, 1200)]:
                value = args.get(key)
                if type(value) is not int or not low <= value <= high:
                    raise ValueError('Viewport dimensions are outside supported bounds')
                request[key] = value
        elif action not in {'observe', 'screenshot'}:
            raise ValueError('Unsupported browser action')
        return request

    def start(self, task, cfg, guard):
        require_host_preview(task)
        self.stop(task['id'])
        url = urlsplit(cfg['url'])
        with socket.socket(socket.AF_INET6 if ':' in url.hostname else socket.AF_INET) as probe:
            try:
                probe.bind((url.hostname, url.port))
            except OSError:
                raise ValueError('Preview port is in use; choose an unused port before authorizing') from None
        before = candidate(task)
        root = Path(tempfile.mkdtemp(prefix='cheapos-browser-'))
        _, snapshot = Workspace.snapshot(task['workspace'], root / 'workspace')
        guard()
        if before != candidate(task):
            raise ValueError('Candidate changed while creating the preview copy')
        if snapshot['skipped']:
            raise ValueError('Preview snapshot omitted files; inspect snapshot exclusions before verification')
        frozen = inputs(root / 'workspace')
        if frozen != inputs(task['workspace']):
            raise ValueError('Preview snapshot does not match the current candidate')
        # Reuse the preview launcher, with an already frozen current-candidate copy.
        run = dict(root=str(root), tip=before, config=cfg, logs='', process=None,
                   stop=threading.Event(), status='starting', prepared=True)
        run['thread'] = threading.Thread(target=self.engine.previews.launch, args=(run, task['workspace']), daemon=True)
        session = {'id': uuid.uuid4().hex, 'candidate': before, 'config': cfg, 'run': run, 'inputs': frozen}
        with self.lock:
            guard()
            if self.authorized(task) != cfg:
                raise ValueError('Browser consent changed during snapshot')
            self.sessions[task['id']] = session
            run['thread'].start()
        # Return while setup/start proceeds; open after status reports running.
        return {'status': 'starting', 'candidate': before, 'next_action': 'Use status, then open when running'}

    @staticmethod
    def validate_copy(session):
        if inputs(Path(session['run']['root']) / 'workspace') != session['inputs']:
            raise ValueError('Preview setup or application changed candidate source files; no current evidence was recorded')

    def open(self, task, runtime):
        cfg = self.authorized(task)
        session = self.sessions.get(task['id'])
        if not session or session['candidate'] != candidate(task) or session['config'] != cfg:
            raise ValueError('Start the current authorized candidate first')
        if session['run']['status'] != 'running':
            return {'status': session['run']['status'], 'logs': session['run']['logs'][-8000:]}
        self.validate_copy(session)
        if session.get('driver'):
            return {'status': 'running', 'candidate': session['candidate']}
        driver = None
        try:
            driver = Driver()
            with self.lock:
                if self.sessions.get(task['id']) is not session:
                    raise InterruptedError('Browser session was stopped during launch')
                session['driver'] = driver
            result = driver.call({'action': 'open', 'url': cfg['url']}, runtime.guard)
            runtime.guard()
            if self.sessions.get(task['id']) is not session or session['candidate'] != candidate(task):
                raise InterruptedError('Browser session stopped or candidate changed')
            if result.get('error'):
                session['driver'].close()
                session.pop('driver', None)
            return result
        except BaseException:
            if driver:
                driver.close()
            self.stop(task['id'])
            raise

    def directory(self, task):
        return self.engine.store.root / 'tasks' / task['id'] / 'browser-evidence'

    def save(self, task, record):
        target = self.directory(task) / (record['id'] + '.json')
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(record), encoding='utf-8')
        temporary.chmod(0o600)
        temporary.replace(target)

    def read(self, task, evidence_id=None):
        directory = self.directory(task)
        current = candidate(task)
        if evidence_id is None:
            records = []
            for path in sorted(directory.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
                record = json.loads(path.read_text())
                records.append({k: record[k] for k in ('id', 'candidate', 'action', 'created_at')}
                               | {'current': record['candidate'] == current})
            return {'records': records, 'current_candidate': current}
        if not isinstance(evidence_id, str) or len(evidence_id) != 32 or any(c not in '0123456789abcdef' for c in evidence_id):
            raise ValueError('Invalid browser evidence ID')
        try:
            record = json.loads((directory / (evidence_id + '.json')).read_text())
        except OSError:
            raise ValueError('Browser evidence is missing or unavailable') from None
        grant = task.get('browser_permission')
        if grant and record['config_digest'] != digest(config(grant['config'])):
            raise ValueError('Browser evidence belongs to a different preview configuration')
        if record['candidate'] != current:
            raise ValueError('Browser evidence belongs to a stale candidate')
        if record.get('image_digest'):
            try:
                data = (directory / (evidence_id + '.png')).read_bytes()
            except OSError:
                raise ValueError('Browser screenshot is missing or unavailable') from None
            if hashlib.sha256(data).hexdigest() != record['image_digest']:
                raise ValueError('Browser screenshot changed; evidence is invalid')
        return record

    def image_path(self, task, reference):
        evidence_id = reference.removeprefix('browser:')
        record = self.read(task, evidence_id)
        if not record.get('image_digest') or record['result'].get('error'):
            raise ValueError('Browser evidence has no successful screenshot')
        return self.directory(task) / (evidence_id + '.png')
