"""Durable alternative-worker recovery for observed implementation stalls."""
from .model_pool import automatic
from . import branch_workspace


def queue(controller, runtime, item):
    engine=controller.engine;task=runtime.task;run=task['branch_run']
    # These are implementation failures, not permission/setup/review/user waits.
    from .continuation_policy import implementation_handoff, record
    if not implementation_handoff(task, item, runtime.stop.is_set()) or not automatic(task,'worker'):
        return False
    record(task, 'implementation_handoff')
    last_check=(task.get('checks') or [{}])[-1]
    if last_check.get('next_action')==task.get('error'):
        return False
    runtime.guard()
    controller.validate_authority(task,run)
    branch_workspace.validate_owned(run['workspace_mapping'],run['expected_feature_tip'])
    if any(not controller.scopes.authorize(task,scope['command']) for scope in run['check_scope']):
        return False
    recovery=run.setdefault('implementation_recovery',{'attempts':0,'failed_models':[]})
    per_item=item.setdefault('recovery',{'attempts':0})
    worker=(task.get('providers',{}).get('worker') or {}).get('model')
    if not worker:return False
    # A queued or already failed worker is not a new strategy. The authorized
    # pool and task budget, not a separate handoff count, bound continuation.
    if worker in recovery['failed_models']:
        return False
    recovery['attempts']+=1;per_item['attempts']+=1
    if worker not in recovery['failed_models']:recovery['failed_models'].append(worker)
    reason=task.get('error') or 'Implementation made no further progress.'
    brief=task.pop('coordinator_handoff_brief',None)
    if brief: reason += '\nCoordinator continuation (advisory, same scope and permissions): ' + brief
    task['route'].setdefault('recovery',{})['worker']={'from':worker,'reason':reason}
    task.update(status='running',error=None,error_code=None,answer_pending=False,action_pending=True)
    task['loop_guidance'] = 'Continue the unfinished item from saved changes and failing check evidence. Inspect the relevant code, repair the concrete failures, then verify and submit checkpoint for independent review.'
    task.pop('recovery_blocked',None)
    runtime.step_turns=0
    runtime.observations.clear();runtime.file_observations.clear();runtime.edit_versions.clear()
    runtime.action_context_ready=False;runtime.compact_context_ready=False
    engine.event(task,'worker_recovery','Trying another free worker for the unfinished item',
                 {'item_id':item['id'],'from':worker,'attempt':recovery['attempts'],'reason':reason})
    # Persist before dispatch. Restart/Resume cannot refund an attempted handoff.
    engine.store.save(task)
    return True
