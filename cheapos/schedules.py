"""Device-local recurrence of operator-approved plans. Models cannot schedule work.

Each occurrence gets new task/check/command receipts. A durable task ID is claimed
before preparation; restart never converts an uncertain dispatch into a new run.
"""
import copy
import json
import math
import threading
import time
import uuid

from .branch_authorization import digest
from .branch_runs import require_supported, validate_plan
from .branch_workspace import inspect_source
from .storage import write_json
from .test_policy import plan_commands

INTERVALS = (6, 12, 24, 168)


class Schedules:
    def __init__(self, engine, clock=time.time):
        self.engine, self.clock = engine, clock
        self.path = engine.store.root / 'schedules.json'
        self.stop = threading.Event()
        self.thread = None
        self.dispatching = set()
        self.error = None
        self.records = {}
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text())
                if data.get('version') != 1 or not isinstance(data.get('schedules'), dict):
                    raise ValueError('Unsupported schedules file')
                for key, record in data['schedules'].items():
                    if record['id'] != key or record['interval_hours'] not in INTERVALS or type(record['enabled']) is not bool:
                        raise ValueError('Invalid schedule')
                    if digest(record['template']) != record['template_digest']:
                        raise ValueError('Saved schedule authority changed')
                    if (not isinstance(record['name'], str) or not isinstance(record['history'], list)
                            or not isinstance(record['last_task_id'], str)
                            or type(record['next_due']) not in (int, float) or not math.isfinite(record['next_due'])
                            or record['allow_task_commands'] is not True
                            or type(record['full_suite_approved']) is not bool
                            or validate_plan(record['template']['plan'])['limits'].get('dollars') != 0):
                        raise ValueError('Invalid schedule authority')
                    record.setdefault('error', None)
                self.records = data['schedules']
        except (OSError, ValueError, KeyError, TypeError):
            self.error = 'Saved schedules could not be loaded. No scheduled work will start; restore the saved file.'

    def save(self):
        if self.error:
            raise ValueError(self.error)
        write_json(self.path, {'version': 1, 'schedules': self.records})

    def preview(self, task_id):
        with self.engine.lock:
            task = self.engine.store.get(task_id)
            run = require_supported(task.get('branch_run'))
            if not run.get('authorization_ref') or task.get('trashed_at'):
                raise ValueError('Schedule an approved Unattended plan from an active or archived chat')
            snapshot = task.get('settings_snapshot')
            if not snapshot:
                raise ValueError('This older task has no captured settings. Approve a new plan before scheduling it.')
            self.engine.settings_policy(snapshot)
            if run['plan']['limits'].get('dollars') != 0:
                raise ValueError('Scheduled tasks currently require a $0 API spending allowance. Approve a zero-spend plan first.')
            template = {'repository': task['source'], 'project': inspect_source(task['source']),
                        'prompt': task['prompt'], 'plan': validate_plan(run['plan']),
                        'inputs': copy.deepcopy(run.get('inputs', {})),
                        'target_ref': run['target_ref'], 'settings_snapshot': copy.deepcopy(snapshot)}
            return {'task_id': task_id, 'template': template, 'approval_digest': digest(template),
                    'full_suite_checks': plan_commands(template['plan'])}

    def create(self, values):
        allowed = {'task_id', 'name', 'interval_hours', 'approval_digest', 'approved', 'allow_task_commands', 'full_suite_approved'}
        if not isinstance(values, dict) or set(values) - allowed:
            raise ValueError('Provide the displayed schedule and permission decisions')
        if values.get('approved') is not True or values.get('allow_task_commands') is not True:
            raise ValueError('Approve recurring runs and commands in their separate task copies')
        interval = values.get('interval_hours')
        if type(interval) is not int or interval not in INTERVALS:
            raise ValueError('Choose a supported repeat interval')
        name = values.get('name', '')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError('Use a schedule name of 1–120 characters')
        with self.engine.lock:
            preview = self.preview(values.get('task_id'))
            if preview['approval_digest'] != values.get('approval_digest'):
                raise ValueError('The task setup changed. Inspect the schedule again before approving.')
            if preview['full_suite_checks'] and values.get('full_suite_approved') is not True:
                raise ValueError('Repeating full-suite checks needs explicit approval')
            if any(r['template_digest'] == preview['approval_digest'] for r in self.records.values()):
                raise ValueError('This plan already has a schedule. Manage it in Settings → Scheduled tasks.')
            now = self.clock()
            record = {'id': uuid.uuid4().hex, 'name': name.strip(), 'interval_hours': interval,
                      'enabled': True, 'next_due': now + interval * 3600, 'created_at': now,
                      'template_task_id': values['task_id'], 'template': preview['template'],
                      'template_digest': preview['approval_digest'], 'allow_task_commands': True,
                      'full_suite_approved': values.get('full_suite_approved') is True,
                      'last_task_id': values['task_id'], 'history': [], 'error': None}
            self.records[record['id']] = record
            self.save()
            return self.view()

    def update(self, schedule_id, values):
        if not isinstance(values, dict) or set(values) != {'enabled'} or type(values['enabled']) is not bool:
            raise ValueError('Provide a schedule enabled decision')
        with self.engine.lock:
            record = self.records[schedule_id]
            record['enabled'] = values['enabled']
            # Enabling is not a burst of catch-up runs or a task Resume.
            if values['enabled']:
                record['next_due'] = self.clock() + record['interval_hours'] * 3600
            self.save()
            return self.view()

    def waiting(self, record):
        task_id = record.get('last_task_id')
        if not task_id:
            return None
        task = self.engine.store.tasks.get(task_id)
        if not task:
            return 'The previous occurrence is missing or did not finish starting. Inspect saved work before repeating.'
        if task.get('trashed_at'):
            return 'The previous task is in Trash. Restore and resolve it before repeating.'
        run = task.get('branch_run', {})
        if run.get('status') == 'merged':
            return None
        if (run.get('status') == 'ready_for_merge' and run.get('items')
                and all(i.get('status') == 'satisfied_without_change' for i in run['items'])
                and run.get('readiness', {}).get('manifest', {}).get('diff') == ''):
            return None
        return 'Waiting for the previous task to finish and its changes to be merged. Open that chat to continue.'

    def remove(self, schedule_id):
        with self.engine.lock:
            record = self.records[schedule_id]
            if record['enabled'] or schedule_id in self.dispatching:
                raise ValueError('Disable this schedule and let startup finish before removing it')
            del self.records[schedule_id]
            self.save()
            return self.view()

    def view(self):
        with self.engine.lock:
            return {'error': self.error, 'schedules': [
                {**{k: copy.deepcopy(v) for k, v in r.items() if k not in {'template', 'template_digest'}},
                 'repository': r['template']['repository'], 'waiting': self.waiting(r)}
                for r in self.records.values()]}

    def run_now(self, schedule_id):
        with self.engine.lock:
            record = self.records[schedule_id]
            if not record['enabled']:
                raise ValueError('Enable this schedule before running it')
            if reason := self.waiting(record):
                raise ValueError(reason)
            record['error'] = None
            record['next_due'] = self.clock()
            self.save()
        # The scheduler thread dispatches so an HTTP request stays responsive.
        return self.view()

    def tick(self):
        if self.error or self.stop.is_set():
            return
        startup = getattr(self.engine, 'startup', None)
        if startup is not None and startup.busy():
            return
        with self.engine.lock:
            if not self.engine.admission.snapshot()['unattended']['allowed']:
                return
            for item in self.records.values():
                previous = self.engine.store.tasks.get(item.get('last_task_id'), {})
                if item['error'] and previous.get('branch_run', {}).get('status') == 'merged':
                    item['error'] = None
            now = self.clock()
            record = next((r for r in self.records.values() if r['enabled'] and not r['error']
                           and r['next_due'] <= now and r['id'] not in self.dispatching and not self.waiting(r)), None)
            if record is None:
                return
            previous = self.engine.store.get(record['last_task_id'])
            if previous['branch_run']['status'] != 'merged':
                from .branch_final import validate
                try:
                    validate(previous['branch_run']['readiness'], previous)
                except (OSError, ValueError, KeyError):
                    record['error'] = 'The no-change review no longer matches saved work. Open the previous task and recheck.'
                    self.save()
                    return
            task_id = uuid.uuid4().hex
            record['last_task_id'] = task_id
            record['next_due'] = now + record['interval_hours'] * 3600
            record['history'] = (record['history'] + [{'task_id': task_id, 'started_at': now}])[-50:]
            self.save()  # Write-ahead dispatch claim; no duplicate after a crash.
            self.dispatching.add(record['id'])
            # Reserve the existing unattended slot during Git preparation. A
            # foreground start cannot race us and strand an authorized occurrence.
            self.engine.admission.pending[task_id] = 'unattended'
        try:
            template = copy.deepcopy(record['template'])
            if template['plan']['limits'].get('dollars') != 0:
                raise ValueError('Scheduled tasks require a $0 API spending allowance')
            if inspect_source(template['repository']) != template.pop('project'):
                raise ValueError('Project identity changed; approve a new schedule for this project')
            snapshot = template.pop('settings_snapshot')
            values = {**template, 'base_ref': template['target_ref'],
                      'feature_ref': 'refs/heads/feat/scheduled-' + task_id[:16], 'keep_up_to_date': False}
            result = self.engine.branch.prepare(values, captured_settings=snapshot, reserved_task_id=task_id)
            with self.engine.lock:
                task = self.engine.store.get(task_id)
                task['schedule'] = {'id': record['id'], 'name': record['name'], 'template_task_id': record['template_task_id']}
                self.engine.event(task, 'schedule', 'Started by scheduled task: ' + record['name'], task['schedule'])
                self.engine.store.save(task)
                # Disabling during preparation cancels future dispatch too.
                if not record['enabled'] or self.stop.is_set():
                    return
                if task['branch_run']['status'] != 'awaiting_authorization':
                    return  # A concurrent operator pause/revision wins.
                self.engine.admission.pending.pop(task_id, None)
                self.engine.branch.authorize(task_id, {'proposal_id': result['proposal_id'], 'approved': True,
                    'allow_task_commands': record['allow_task_commands'],
                    'full_suite_approved': record['full_suite_approved']}, background=True)
        except Exception as error:
            with self.engine.lock:
                record['error'] = str(error)[:500] if isinstance(error, ValueError) else 'Scheduled startup failed. Inspect the saved task before continuing.'
                self.save()
        finally:
            with self.engine.lock:
                self.dispatching.discard(record['id'])
                self.engine.admission.pending.pop(task_id, None)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        def loop():
            while not self.stop.is_set():
                try:
                    self.tick()
                except Exception:
                    # Do not crash the app or repeatedly dispatch on storage errors.
                    self.error = 'Scheduled task storage needs attention. No further runs will start.'
                self.stop.wait(5)
        self.thread = threading.Thread(target=loop, daemon=True, name='cheapos-schedules')
        self.thread.start()

    def shutdown(self):
        self.stop.set()
