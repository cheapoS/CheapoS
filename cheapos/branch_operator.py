"""Explicit operator direction without changing an approved run's scope."""
import copy
from .branch_authorization import digest


def continue_saved(controller, task_id):
    """Attempt dispatch; retain direction and a precise actionable blocker."""
    engine = controller.engine
    try:
        with engine.lock:
            task = engine.store.get(task_id)
            run = task.get('branch_run') or {}
            if run.get('status') == 'awaiting_authorization' and not run.get('authorization_ref'):
                proposal = controller.proposals.prepare(task_id, controller.contract(task))
                return controller.authorize(task_id, {'proposal_id': proposal['proposal_id'], 'approved': True, 'full_suite_approved': True})
        result = controller.resume(task_id, {})
        if result.get('task'):
            return result['task']
        if result.get('needs_consent'):
            detail = {'status':'needs_consent', 'reason':'Saved work is retained. Confirm the existing verification commands before work can continue.',
                      **{key:copy.deepcopy(result[key]) for key in ('proposal_id','scopes') if key in result}}
        elif result.get('needs_merge_recovery'):
            detail = {'status':'blocked','reason':'Saved work is retained. Finish or inspect the existing local merge operation before running more work.'}
        else:
            detail = {'status':'blocked','reason':'Saved work is retained. Inspect the current run controls before continuing.'}
    except (ValueError, OSError) as error:
        detail = {'status':'blocked','reason':'Saved work is retained. '+str(error)[:1000]}
    with engine.lock:
        task = engine.store.get(task_id)
        task['operator_continue'] = detail
        engine.event(task, 'operator_direction', 'Continuation needs attention', detail)
        return task


def control(controller, task_id, values):
    if not isinstance(values, dict) or set(values)-{'action','approved','message','item_id'}:
        raise ValueError('Use an explicit operator action, not a replacement task record')
    action = values.get('action')
    if action not in {'enable','retry_item'}:
        raise ValueError('Choose enable or retry_item')
    engine = controller.engine
    with engine.lock:
        engine.require_active_task(task_id)
        engine.admission.require_idle(task_id)
        task = engine.store.get(task_id);run = task['branch_run']
        if run['status'] not in {'paused','blocked','running'} or not run.get('authorization'):
            raise ValueError('Choose an authorized unfinished run')
        controller.validate_authority(task,run)
        if action == 'enable':
            if values != {'action':'enable','approved':True}:
                raise ValueError('Explicitly approve operator development mode for this saved run')
            task.setdefault('execution',{})['development_mode'] = True
            task['operator_bounded_work'] = False
            run['development_authorization']={'enabled':True,'authorization_ref':run['authorization_ref'],
                                              'plan_digest':digest(run['authorization']['contract']['plan'])}
            receipt = {'authorization_id':run['authorization_ref'], 'plan_digest':digest(run['plan']),
                       'mode':'operator_development', 'spending':'unchanged', 'source':task['source']}
            task.setdefault('operator_development_history',[]).append(receipt)
            if task.get('settings_snapshot'):
                from .task_settings import sync_saved
                sync_saved(task)
            engine.event(task,'operator_direction','Operator development mode enabled',receipt)
            return task
        from .development import enabled
        if not enabled(task):raise ValueError('Enable operator development mode before applying and continuing a correction')
        if values.get('item_id') != run.get('current_item_id'):
            raise ValueError('Retry the current item; changing task order requires a revised approved plan')
        message = values.get('message')
        if not isinstance(message,str) or not message.strip():
            raise ValueError('Describe the correction to apply to this item')
    return controller.message(task_id,{'message':message})


def revision_token(run, task=None):
    item=next((i for i in run.get('items',[]) if i['id']==run.get('current_item_id')),None)
    return digest({**{key:run.get(key) for key in ('authorization_ref','plan_digest','expected_feature_tip','current_item_id')},
                   'item_instructions':(item or {}).get('instructions'),'plan':run.get('plan'),
                   'worker':(task or {}).get('providers',{}).get('worker'),'reviewer':(task or {}).get('providers',{}).get('reviewer')})


def capabilities(controller, task_id):
    from .branch_planner import is_planning, recovery
    if is_planning(controller.engine.store.get(task_id)): return recovery(controller, task_id)
    from . import access_policy
    from .development import enabled
    task=controller.engine.store.get(task_id);run=task['branch_run']
    current=task.get('providers',{}).get('worker') or {}
    gateway=controller.engine.connection_for(current) if hasattr(controller.engine,"connection_for") else controller.engine.gateway
    policy=access_policy.for_config(task,current) if task.get('gateway_connections') is not None else (task.get('route') or {}).get('access_policy',run.get('model_policy',{}).get('gateway_access'))
    catalog=gateway.catalog(fresh=False)
    used={task.get('providers',{}).get('reviewer',{}).get('model')}
    models=[{'id':m['id'],'label':m.get('name') or m['id']} for m in catalog.get('models',[])
            if access_policy.eligible(m,policy) and m['id'] not in used]
    from .test_policy import disclosure
    from . import reviewer_recovery
    return {**disclosure(controller.engine,task),'enabled':enabled(task),'current_item_id':run.get('current_item_id'),'revision_token':revision_token(run,task),
            'actions':['enable','takeover','retry','model','reviewer','revise','checks'],'models':models,
            'can_reviewer':True,'reviewers':reviewer_recovery.candidates(controller.engine,task),'unknown_worker_history':bool(reviewer_recovery.unknown_workers(task)),
            'can_checks':True,'required_checks':next((i.get('required_checks',[]) for i in run.get('items',[]) if i['id']==run.get('current_item_id')),[]),'final_checks':run['plan'].get('final_checks',[]),
            'scope':'Current uncommitted item only. Spending, checks, reviewer approval and Git safeguards remain unchanged.'}


def amend(controller, task_id, values):
    """An explicit controller-issued replacement contract; old authority is retained."""
    from . import branch_runs, access_policy, branch_workspace
    from .development import enabled
    from .providers import validate_provider
    from .branch_authorization import contract_builder
    action=values.get('action')
    allowed={'action','approved','message','model','instructions','revision_token','required_checks','final_checks','full_suite_approved','resume'}
    if set(values)-allowed or action not in {'model','reviewer','revise','checks'} or values.get('approved') is not True:
        raise ValueError('Explicitly approve the selected model or current-item revision')
    if 'resume' in values and not isinstance(values['resume'],bool):raise ValueError('Resume must be a boolean')
    engine=controller.engine
    with engine.lock:
        engine.require_active_task(task_id);engine.admission.require_idle(task_id)
        task=engine.store.get(task_id);run=task['branch_run']
        if action not in {'checks','reviewer'} and not enabled(task):raise ValueError('Enable operator development mode first')
        if run['status'] not in {'paused','blocked'} or run.get('pending_operations') or run.get('merge_operation') or run.get('target_update'):
            raise ValueError('Pause the run and finish any saved commit operation before revising it')
        controller.validate_authority(task,run)
        if values.get('revision_token')!=revision_token(run,task):
            raise ValueError('The operator review is stale. Reopen the recovery controls before approving changes.')
        branch_workspace.validate_owned(run['workspace_mapping'],run['expected_feature_tip'])
        item=next((i for i in run['items'] if i['id']==run.get('current_item_id')),None)
        if not item or (action!='reviewer' and (item.get('commit_receipt') or item['status'] in branch_runs.DONE)):
            raise ValueError('Select a current uncommitted item')
        old_item=copy.deepcopy(item)
        previous=copy.deepcopy(run['authorization'])
        previous_amendments=copy.deepcopy(run.get('amendments',[]))
        previous_final_evidence=copy.deepcopy(run.get('final_evidence',{}))
        policy=copy.deepcopy(run['model_policy'])
        if action in {'model','reviewer'}:
            role='reviewer' if action=='reviewer' else 'worker'
            if action=='reviewer':
                from . import reviewer_recovery
                if reviewer_recovery.unknown_workers(task):raise ValueError('Repair missing worker model provenance before selecting a reviewer')
            chosen=values.get('model')
            available=capabilities(controller,task_id)['reviewers' if action=='reviewer' else 'models']
            if chosen not in {m['id'] for m in available}:raise ValueError('Choose an eligible free or already-included model distinct from the other role and saved authors')
            current=task.get('providers',{}).get(role) or {}
            gateway=engine.connection_for(current) if hasattr(engine,"connection_for") else engine.gateway
            access=access_policy.for_config(task,current) if task.get('gateway_connections') is not None else policy.get('gateway_access')
            access_policy.validate_current(access,access_policy.effective_settings(task,gateway.settings))
            endpoint=gateway.settings['base_url']
            current=task.get('providers',{}).get(role) or {}
            if current.get('gateway')!='omniroute' or current.get('base_url')!=endpoint:
                raise ValueError('Model replacement must stay on this run’s authorized OmniRoute connection')
            cfg=validate_provider({**current,'gateway':'omniroute','base_url':endpoint,'model':chosen,'input_rate':0,'output_rate':0},role)
            for field in ('access','access_binding','pricing_source','catalog_pricing'):cfg.pop(field,None)
            if access is not None:cfg['access_binding']=copy.deepcopy(access)
            model=next(m for m in gateway.catalog(fresh=False)['models'] if m['id']==chosen)
            if access_policy.classify(model,access)=='included':cfg=access_policy.bind_provider(cfg,access,model)
            task.setdefault('operator_model_history',[]).append({'provider':copy.deepcopy(current),'route_recovery':copy.deepcopy((task.get('route') or {}).get('recovery',{}))})
            task['providers'][role]=cfg
            task['operator_'+role+'_model']=chosen
            if action=='reviewer':
                task.pop('reviewer_identity_recovery',None)
            policy['execution']=copy.deepcopy(task['execution']);policy['providers']=copy.deepcopy(task['providers'])
            if task.get('route'):
                task['route'].setdefault('preferred',{})[role]=chosen
                task['route'].get('recovery',{}).pop(role,None)
        elif action=='checks':
            from . import test_policy
            from .engine import check_argv
            from .branch_evidence import commands
            required=values.get('required_checks');final=values.get('final_checks')
            if not all(isinstance(v,list) and v and len(v)<=12 and all(isinstance(c,str) and c.strip() for c in v) for v in (required,final)):
                raise ValueError('Provide one or more executable commands for both item and final verification')
            revised=copy.deepcopy(run['plan'])
            next(i for i in revised['items'] if i['id']==item['id'])['required_checks']=required
            revised['final_checks']=final
            if 'instructions' in values:
                instructions=values['instructions']
                if not isinstance(instructions,str) or not instructions.strip() or len(instructions)>4000:raise ValueError('Provide instructions of up to 4,000 characters')
                next(i for i in revised['items'] if i['id']==item['id'])['instructions']=instructions.strip()
            revised=branch_runs.validate_plan(revised)
            candidate=copy.deepcopy(task);candidate['branch_run']['plan']=revised
            test_policy.approve(candidate,values.get('full_suite_approved'))
            all_commands=[]
            for spec in [c for i in revised['items'] for c in i['required_checks']]+final:
                command=commands([spec])[0]
                import shlex
                check_argv(shlex.join(command))
                if command not in all_commands:all_commands.append(command)
            scopes=[controller.scopes.prepare(task,c) for c in all_commands]
            run['plan']=revised;item['required_checks']=required
            item['instructions']=next(i for i in revised['items'] if i['id']==item['id'])['instructions']
            run['check_scope']=scopes;run['test_policy_version']=1
            task['full_suite_approval']=candidate['full_suite_approval']
            task['check_command']=commands([required[0]])[0]
            task.pop('validated_check_command',None)
            for scope in scopes:controller.scopes.consent(task,scope)
        else:
            instructions=values.get('instructions')
            if not isinstance(instructions,str) or not instructions.strip() or len(instructions)>4000:
                raise ValueError('Provide current-item instructions of up to 4,000 characters')
            spec=next(i for i in run['plan']['items'] if i['id']==item['id'])
            spec['instructions']=instructions.strip();item['instructions']=instructions.strip()
            run['plan']=branch_runs.validate_plan(run['plan'])
        run.setdefault('operator_revision_history',[]).append({'authorization':previous,'amendments':previous_amendments,
            'item_id':item['id'],'item':old_item,'action':action,'final_evidence':previous_final_evidence,'expected_feature_tip':run['expected_feature_tip']})
        run['amendments']=[]
        run['plan_revision']+=1;run['plan_digest']=digest(run['plan']);run['model_policy']=policy
        if action=='reviewer':
            if task.get('pending_review'):
                task.setdefault('operator_review_history',[]).append(copy.deepcopy(task['pending_review']))
            task.pop('pending_review',None)
            task['fresh_review']=True
            task['active_role']='worker'
        else:
            item.setdefault('operator_evidence_history',[]).append({key:copy.deepcopy(item[key]) for key in ('evidence','ready_receipt','review_repair','review_rounds') if key in item})
            item['revision']=item.get('revision',1)+1;item['evidence']={};item['status']='working'
            task['active_role']='worker'
            # Retain worker history; the continuation adapter admits the new scope.
            task.setdefault('conversation_state', {}).setdefault('snapshot_hashes', {}).clear()
            for key in ('ready_receipt','review_repair'):item.pop(key,None)
            for key in ('pending_checkpoint','pending_review','recovery_blocked'):task.pop(key,None)
            run.pop('readiness',None);run['final_evidence']={}
        contract=contract_builder(run,run['authorization_workspace'],policy,run['check_scope'])
        proposal=controller.proposals.prepare(task_id,contract)
        auth=controller.proposals.authorize(task_id,proposal['proposal_id'],True,contract)
        run['authorization']=auth;run['authorization_ref']=auth['id']
        if run.get('development_authorization'):
            run['development_authorization']['authorization_ref']=auth['id']
            run['development_authorization']['plan_digest']=digest(contract['plan'])
        if task.get('settings_snapshot'):
            from .task_settings import sync_saved
            sync_saved(task)
        engine.event(task,'operator_revision','Approved '+('reviewer model replacement' if action=='reviewer' else 'worker model replacement' if action=='model' else 'verification requirements' if action=='checks' else 'current-item revision'),
                     {'action':action,'item_id':item['id'],'model':task['providers']['reviewer' if action=='reviewer' else 'worker']['model'],'authorization_ref':auth['id']})
        if values.get('resume') is False:
            task['operator_continue']={'status':'ready','reason':'Revised requirements saved. The task remains paused until you continue.'}
            engine.store.save(task)
            return task
    if action=='reviewer':return continue_saved(controller,task_id)
    message=values.get('message') or ('Continue the current item with the approved '+('worker model.' if action=='model' else 'revised verification commands. Run only the checks now in scope and do not claim the replaced checks passed.' if action=='checks' else 'revised instructions.'))
    result=controller.message(task_id,{'message':message})
    if action=='checks' and not enabled(result):return continue_saved(controller,task_id)
    return result


def recover(controller, task_id, values):
    from .branch_planner import is_planning, recovery
    if is_planning(controller.engine.store.get(task_id)): return recovery(controller, task_id, values)
    action=values.get('action')
    if action in {'model','reviewer','revise','checks'}:return amend(controller,task_id,values)
    if action=='takeover':
        if set(values)-{'action','approved','message'} or values.get('approved') is not True:
            raise ValueError('Explicitly approve takeover with your correction')
        message=values.get('message')
        if not isinstance(message,str) or not message.strip() or len(message)>8000:raise ValueError('Enter a correction of up to 8,000 characters')
        with controller.engine.lock:
            task=control(controller,task_id,{'action':'enable','approved':True})
            try:
                for captured in task['branch_run']['check_scope']:
                    scope=controller.scopes.prepare(task,captured['command'])
                    controller.scopes.consent(task,scope)
            except (ValueError,OSError):
                # Direction is still captured below; resume explains the exact
                # environmental/identity blocker without granting invalid scope.
                pass
            return controller.message(task_id,{'message':message})
    if action=='retry':
        from .development import enabled
        if set(values)-{'action','message'}:raise ValueError('Retry accepts only a correction message')
        if not enabled(controller.engine.store.get(task_id)):raise ValueError('Enable operator development mode first')
        return controller.message(task_id,{'message':values.get('message') or 'continue'})
    return control(controller,task_id,values)
