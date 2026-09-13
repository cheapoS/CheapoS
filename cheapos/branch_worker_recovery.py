"""Durable alternative-worker recovery for observed implementation stalls."""
from .model_pool import automatic, MAX_HANDOFFS
from . import branch_workspace


def queue(controller, runtime, item):
    engine=controller.engine;task=runtime.task;run=task['branch_run']
    # These are implementation failures, not permission/setup/review/user waits.
    if (task.get('status')!='paused' or task.get('error_code')!='progress_limit'
            or item.get('status')!='working' or runtime.stop.is_set()
            or not automatic(task,'worker') or task.get('active_role')!='worker'
            or run.get('waiting_for_user') or task.get('pending_approval')
            or task.get('pending_review') or task.get('limit_hit')):
        return False
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
    if recovery['attempts']>=MAX_HANDOFFS or per_item['attempts']>=MAX_HANDOFFS or runtime.handoffs>=MAX_HANDOFFS:
        task['error']='Automatic model recovery allowance is exhausted. Saved files and usage are retained; Resume does not renew attempts.'
        return False
    worker=(task.get('providers',{}).get('worker') or {}).get('model')
    if not worker:return False
    recovery['attempts']+=1;per_item['attempts']+=1
    if worker not in recovery['failed_models']:recovery['failed_models'].append(worker)
    reason=task.get('error') or 'Implementation made no further progress.'
    task['route'].setdefault('recovery',{})['worker']={'from':worker,'reason':reason}
    task.update(status='running',error=None,error_code=None,answer_pending=False,action_pending=True,compact_edits=True)
    task.pop('recovery_blocked',None)
    runtime.step_turns=0
    runtime.observations.clear();runtime.file_observations.clear();runtime.edit_versions.clear()
    runtime.action_context_ready=False;runtime.compact_context_ready=False
    engine.event(task,'worker_recovery','Trying another free worker for the unfinished item',
                 {'item_id':item['id'],'from':worker,'attempt':recovery['attempts'],'reason':reason})
    # Persist before dispatch. Restart/Resume cannot refund an attempted handoff.
    engine.store.save(task)
    return True
