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
    if any(not controller.scopes.authorize(task,scope['command'],directory=scope.get('check_directory','.')) for scope in run['check_scope']):
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


def restore_local_repair_routes(engine, runtime):
    """Reclassify the specific legacy pre-dispatch reference failure on Resume.

    Keep all attempts, findings and usage. Only a matching saved local error and
    an undispatched request can remove an implementation exclusion. Gateway
    health, probe rejections, independent review and access policy are untouched.
    """
    task=runtime.task;run=task.get('branch_run',{})
    recovery=run.get('implementation_recovery',{})
    if not recovery.get('failed_models'):return
    item=next((i for i in run.get('items',[]) if i['id']==run.get('current_item_id')),None)
    if not item or not item.get('review_repair',{}).get('requirement_refs'):return
    from .branch_disagreement import pending
    pending(task,item)
    prefix='Defect criterion must match a supplied acceptance criterion:'
    restored=[]
    for model in list(recovery['failed_models']):
        events=[e for e in task.get('events',[]) if e.get('kind')=='worker_recovery' and e.get('detail',{}).get('from')==model]
        if not events or any(e['detail'].get('item_id')!=item['id'] or not e['detail'].get('reason','').startswith(prefix) for e in events):continue
        matched=[]
        for event in events:
            requests=[m for m in task.get('request_metrics',[]) if m.get('model')==model and m.get('role')=='worker'
                      and m.get('purpose')=='work' and m.get('branch_item_id')==item['id']
                      and m.get('run_id')==event.get('run_id') and m.get('requested_at','')<event.get('time','')]
            metric=max(requests,key=lambda m:m.get('requested_at',''),default={})
            if not (metric.get('status')=='failed' and metric.get('dispatched') is False and not metric.get('error_code')
                    and metric.get('failure_category')=='invalid_response' and 'reservation' not in metric):break
            matched.append(metric)
        if len(matched)!=len(events):continue
        recovery.setdefault('reclassified_failures',[]).append({'model':model,'item_id':item['id'],
            'event_ids':[e['id'] for e in events], 'request_ids':[m['id'] for m in matched], 'reason':'controller_repair_reference'})
        recovery['failed_models'].remove(model);runtime.failed_models.discard(model)
        for metric in matched:
            metric['original_failure_category']=metric['failure_category']
            metric.update(failure_category='local_controller',error_code='controller_error')
        restored.append(model)
    if restored:
        # A saved wait was chosen with these models excluded. Recompute route
        # eligibility before sleeping; each provider's actual cooldown remains
        # in the health pool and is still enforced by ordinary selection.
        if task.get('retry_wait_enabled'):
            task.update(retry_wait_enabled=False,route_wait=None,route_resume_on_start=False)
            task.pop('route_unavailable',None)
            runtime.route_wait_started_at=None
        queued=task.get('route',{}).get('recovery',{}).get('worker',{})
        if queued.get('from') in restored and queued.get('reason','').startswith(prefix):
            task['route']['recovery'].pop('worker')
        engine.event(task,'routing_repair','Restored routes excluded by a local review-reference error',
                     {'models':restored,'item_id':item['id'],'summary':'Saved review evidence and usage are retained. Ordinary route checks still apply.'})
        engine.store.save(task)
