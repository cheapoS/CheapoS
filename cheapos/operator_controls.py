"""Explicit operator controls: retain evidence, authorization and request history."""
import copy
from .development import enabled
from . import access_policy
from .providers import validate_provider


def model_choices(engine, task):
    """Only existing eligible gateway routes, never invented provider IDs."""
    current=task.get('providers',{}).get('worker') or {}
    gateway=engine.connection_for(current) if hasattr(engine,'connection_for') else engine.gateway
    policy=access_policy.for_config(task,current) if task.get('gateway_connections') is not None else (task.get('route') or {}).get('access_policy') or task.get('access_policy')
    if not policy: return []
    catalog=gateway.catalog(fresh=False)
    if catalog.get('status')!='ready':return []
    reviewer=(task.get('providers',{}).get('reviewer') or {}).get('model')
    return [{'id':m['id'],'label':m['id']} for m in catalog.get('models',[])
            if m['id']!=reviewer and m.get('tool_calling') is True and access_policy.eligible(m,policy)]


def interactive(engine, task_id, values=None):
    with engine.lock:
        engine.require_active_task(task_id)
        task=engine.store.get(task_id)
        if task.get('branch_run'):raise ValueError('Use the branch operator controls')
        runtime=engine.runtimes.get(task_id)
        busy=bool(runtime and runtime.thread and runtime.thread.is_alive())
        usable=not busy and not task.get('demo') and not task.get('commit_pending')
        from .progress import digest
        revision=digest([task.get('patch'),task.get('requests'),task.get('providers'),task.get('execution')])
        if values is None:
            return {'revision_token':revision,'enabled':enabled(task),'can_enable':usable and not enabled(task),
                    'can_retry':usable and enabled(task),'can_model':usable and enabled(task),
                    'can_revise':False,'models':model_choices(engine,task) if usable else [],
                    'reason':'Pause active work before changing its configuration.' if busy else ''}
        if not usable:raise ValueError('Pause active work or finish the pending commit before changing recovery settings')
        if not isinstance(values,dict) or set(values)-{'action','message','model','instructions','approved','revision_token'}:raise ValueError('Invalid recovery action')
        action=values.get('action')
        if action not in {'enable','takeover','retry','model'}:raise ValueError('Choose enable, retry or a worker model')
        if action in {'enable','takeover','model'} and values.get('approved') is not True:
            raise ValueError('Approve this recovery configuration change explicitly')
        if action not in {'enable','takeover'} and not enabled(task):raise ValueError('Enable development mode for this task first')
        message=values.get('message') or 'continue'
        if not isinstance(message,str) or not 1<=len(message.strip())<=8000:raise ValueError('Enter a direction of up to 8,000 characters')
        if action=='model':
            if values.get('revision_token')!=revision:raise ValueError('The task changed. Refresh recovery choices before changing its worker.')
            selected=values.get('model')
            if selected not in {m['id'] for m in model_choices(engine,task)}:raise ValueError('Choose an eligible configured route distinct from the reviewer')
            current=task.get('providers',{}).get('worker') or {}
            gateway=engine.connection_for(current)
            policy=access_policy.for_config(task,current) if task.get('gateway_connections') is not None else (task.get('route') or {}).get('access_policy') or task.get('access_policy')
            catalog=gateway.catalog(fresh=False)
            entry=next(m for m in catalog['models'] if m['id']==selected)
            config=validate_provider({**current,'gateway_type':gateway.settings.get('gateway_type','omniroute'),'gateway':'omniroute','base_url':gateway.settings['base_url'],'model':selected,'input_rate':0,'output_rate':0,'key_env':task.get('providers',{}).get('worker',{}).get('key_env')},'worker')
            config['access_binding']=copy.deepcopy(policy)
            if access_policy.classify(entry,policy)=='included':
                config=access_policy.bind_provider(config,policy,entry)
            task.setdefault('operator_model_history',[]).append(copy.deepcopy(task['providers'].get('worker')))
            task['providers']['worker']=config
            task['operator_worker_model']=selected
            task.setdefault('operator_route_history',[]).append(copy.deepcopy(task.get('route',{})))
            if task.get('route'):
                task['route'].get('recovery',{}).pop('worker',None)
                task['route'].setdefault('preferred',{})['worker']=selected
        if action == 'model':
            from .task_settings import sync_saved
            sync_saved(task)
        if action in {'enable','takeover'}:
            task['execution']={**task.get('execution',{}),'development_mode':True}
            task['limits']['uncapped_work']=True
            task['operator_bounded_work']=False
            from .task_settings import sync_saved
            sync_saved(task)
            engine.event(task,'operator_control','Development mode enabled for this task',
                         'Work and recovery caps are off. Usage, spending policy, permissions and independent review are retained.')
            engine.store.save(task)
            task['operator_continue']={'status':'ready','reason':'Development mode is enabled. Send your direction or choose Continue.'}
            engine.store.save(task)
            if action=='enable':return {'task':task,'operator_continue':task['operator_continue']}
        engine.store.save(task)
        # A real operator request creates a new direction, preserving total usage.
        try:
            started=engine.start(task_id,{'message':message.strip()})
            active=engine.runtimes[task_id].task
            active['operator_continue']={'status':'running','reason':'Continuing from saved files with your direction.'}
            engine.store.save(active)
            return {'task':engine.store.get(task_id),'operator_continue':active['operator_continue']}
        except ValueError as error:
            task=engine.store.get(task_id)
            task['steer_guidance']=message.strip()
            engine.event(task,'steer','You',message.strip())
            task['operator_continue']={'status':'blocked','reason':str(error)}
            engine.store.save(task)
            return {'task':task,'operator_continue':task['operator_continue']}
