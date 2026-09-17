"""Persist an exact merge approval before doing slow Git work in the background."""
import copy
import threading

from . import branch_pause, branch_runs as state

LABELS = {'accepted': 'Merge approval saved', 'checking': 'Checking reviewed changes',
          'integrating': 'Merging locally', 'confirming': 'Confirming merge',
          'completed': 'Merged locally'}


def progress(controller, task, stage):
    with controller.engine.lock:
        task['branch_run']['merge_progress'] = {
            'status': 'completed' if stage == 'completed' else 'running',
            'stage': stage, 'label': LABELS[stage]}
        controller.engine.event(task, 'branch_integration', LABELS[stage], {'stage': stage})


def start(controller, task_id, values):
    from .branch_completion import _proposal
    engine = controller.engine
    with engine.lock:
        task = engine.store.get(task_id)
        run = state.require_supported(task['branch_run'])
        recovering = values == {'approved': True, 'recover': True}
        contract = None if recovering else _proposal(controller, task_id, values, 'merge')
        saved = run.get('merge_operation') or run.get('merge_receipt')
        if saved:
            # A lost response or double click returns the SAME saved operation.
            if contract and contract['operation']['id'] != saved['id']:
                raise ValueError('A different merge already owns this run')
            if run['status'] == 'merged' or task_id in engine.admission.operations:
                return copy.deepcopy(task)
        engine.require_active_task(task_id)
        engine.admission.require_idle(task_id)
        controller.validate_authority(task, run)
        if recovering:
            if not run.get('merge_operation'):
                raise ValueError('No saved local merge operation to finish')
        elif not saved:
            if contract['run_id'] != run['id'] or contract['readiness_id'] != run.get('readiness', {}).get('id'):
                raise ValueError('Readiness changed after preview')
            if run.get('readiness', {}).get('integration_blocker'):
                raise ValueError(run['readiness']['integration_blocker'])
            auth = controller.final_proposals.authorize(task_id, values['proposal_id'], True, contract)
            run.update(merge_authorization=auth, merge_authorization_ref=auth['id'],
                       merge_operation=copy.deepcopy(contract['operation']),
                       merge_preview_id=values['proposal_id'])
        # All Git/evidence checks remain in _integrate and run again immediately
        # before mutation. This receipt acknowledges consent, never a successful merge.
        if saved:
            # Recovery re-enters the journaled operation, not the worker loop.
            run['status'] = 'merging'
        else:
            state.transition(run, 'merging')
        branch_pause.clear(run)
        run.pop('pause_reason', None)
        task.update(status='running', error=None, stream=None, check_stream=None)
        progress(controller, task, 'accepted')
        receipt = copy.deepcopy(task)
        engine.admission.operations[task_id] = None  # Reserve before dispatch.
        thread = threading.Thread(target=complete, args=(controller, task_id), daemon=True)
        try:
            thread.start()
        except Exception as error:
            try: failed(controller, task_id, error)
            finally: engine.admission.operations.pop(task_id, None)
            raise
        return receipt


def failed(controller, task_id, error):
    engine = controller.engine
    with engine.lock:
        task = engine.store.get(task_id)
        diagnostic = branch_pause.PauseError('branch_drift', stage='merging',
            diagnostic={'kind': 'safe_message', 'message': str(error)})
        detail = branch_pause.apply(task, diagnostic)
        task['branch_run'].setdefault('merge_progress', {}).update(status='failed', error=detail['explanation'])
        engine.event(task, 'branch_integration', 'Local merge could not finish', {'error': detail['explanation']})


def complete(controller, task_id):
    from .branch_completion import _integrate
    engine = controller.engine
    try:
        with engine.lock:
            engine.admission.operations[task_id] = threading.get_ident()
            source = engine.store.get(task_id)['branch_run']['workspace_mapping']['source']
        with engine.admission.repository(source):
            _integrate(controller, task_id, {'approved': True, 'recover': True},
                       progress=lambda task, stage: progress(controller, task, stage))
    except Exception as error:
        failed(controller, task_id, error)
    finally:
        with engine.lock:
            engine.admission.operations.pop(task_id, None)
