"""Acknowledge durable approval before journaled, cancelable startup work."""
import copy
import threading

from . import branch_pause

LABELS = {
    'accepted': 'Approval saved',
    'verifying_snapshot': 'Verifying task copy',
    'preparing_branch': 'Preparing branch',
    'preparing_permissions': 'Preparing approved checks',
    'selecting_worker': 'Selecting worker',
}


def progress(controller, runtime, stage):
    with controller.engine.lock:
        if runtime.stop.is_set():
            raise InterruptedError('Startup paused by you')
        task = runtime.task
        controller.validate_authority(task, task['branch_run'])
        startup = task['branch_run']['startup']
        if startup['stage'] == stage: return
        startup.update(stage=stage, label=LABELS[stage])
        controller.engine.event(task, 'branch_startup', LABELS[stage], {'stage': stage})


def start(controller, task):
    """Caller holds engine.lock; reserve the slot before returning a receipt."""
    from .engine import Runtime, now
    engine = controller.engine
    engine.require_active_task(task['id'])
    engine.admission.require('unattended', task['id'])
    runtime = Runtime(task)
    task['branch_run']['startup'] = {'status': 'running', 'stage': 'accepted',
                                    'label': LABELS['accepted'], 'started_at': now()}
    task.update(status='running', error=None)
    engine.event(task, 'branch_startup', 'Approval saved. Preparing your run.', {'stage': 'accepted'})
    receipt = copy.deepcopy(task)
    runtime.thread = threading.Thread(target=complete, args=(controller, runtime), daemon=True)
    engine.runtimes[task['id']] = runtime
    try:
        runtime.thread.start()
    except Exception as error:
        failed(controller, runtime, error)
        raise
    return receipt


def failed(controller, runtime, error):
    with controller.engine.lock:
        task = runtime.task
        run = task['branch_run']
        unstarted = run['status'] == 'awaiting_authorization'
        detail = branch_pause.apply(task, error, cause='operator' if runtime.stop.is_set() else None, stage='startup')
        # Keep the existing explicit "Finish saved startup" recovery path; a
        # durable approval is not evidence that workspace setup completed.
        if unstarted: run['status'] = 'awaiting_authorization'
        run['startup'].update(status='paused' if runtime.stop.is_set() else 'failed', error=detail['explanation'])
        controller.engine.event(task, 'branch_startup', 'Startup paused' if runtime.stop.is_set() else 'Startup needs attention',
                                {'stage': run['startup']['stage'], 'error': detail['explanation']})


def complete(controller, runtime):
    try:
        controller._finish_start(runtime.task, runtime=runtime)
    except Exception as error:
        failed(controller, runtime, error)
