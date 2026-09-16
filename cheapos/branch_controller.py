from . import branch_pause
"""Operator-facing branch-run proposals. Models cannot call this service."""
import copy
import hashlib
import json
import shlex
import uuid
from pathlib import Path

from . import branch_runs as state
from . import branch_workspace as work
from . import branch_evidence as evidence
from .branch_authorization import ProposalRegistry, CheckScopes, contract_builder, digest
from .storage import write_json
from .workspace import Workspace


def policy_for_saved(current, saved):
    """Match only newly optional empty defaults, retaining old contract digests."""
    result = copy.deepcopy(current)
    if isinstance(saved, dict):
        # Development mode is a default for new tasks. Existing authority keeps
        # its captured choice; a later takeover uses an explicit task receipt.
        old_execution=saved.get('execution')
        new_execution=result.get('execution')
        if isinstance(old_execution,dict) and isinstance(new_execution,dict):
            if 'development_mode' in old_execution:
                new_execution['development_mode']=old_execution['development_mode']
            else:new_execution.pop('development_mode',None)
        for section, field, empty in (('execution', 'local_planner', ''), ('providers', 'planner', None), ('execution', 'coordinator_assistance', False), ('execution', 'coordinator_model', ''), ('execution','development_mode',False)):
            old = saved.get(section)
            new = result.get(section)
            if isinstance(old, dict) and isinstance(new, dict) and field not in old and new.get(field) == empty:
                new.pop(field, None)
        for role in ('worker', 'reviewer', 'planner'):
            old_p = (saved.get('providers') or {}).get(role) or {}
            new_p = (result.get('providers') or {}).get(role) or {}
            for field in ('access_binding', 'pricing_source', 'catalog_pricing'):
                if field not in old_p and field in new_p:
                    new_p.pop(field, None)
            if old_p.get('access') == 'included' and 'access' not in new_p:
                new_p['access'] = 'included'
        if 'gateway_access' in saved and 'gateway_access' in result:
            if result['gateway_access'].get('connection_revision') == saved['gateway_access'].get('connection_revision'):
                result['gateway_access']['included_models'] = copy.deepcopy(saved['gateway_access'].get('included_models', []))
    return result


def restore_planning_allowance(task):
    """Execution edits cannot retroactively authorize more planning work."""
    from .engine import limits_from
    limits=copy.deepcopy(task['planning_limits'])
    if run_limits(limits,3)!=limits:
        raise ValueError('Saved planning allowance is incomplete')
    measurement=task.get('planning_request',{}).get('measurement',False)
    if type(measurement) is not bool:raise ValueError('Saved planning measurement choice is invalid')
    original=task.get('planning_task_limits')
    if original is None:
        original=limits_from({'dollars':limits['dollars'],
            'run_minutes':max(1,(limits['working_seconds']+59)//60),
            'reviewer_tokens':limits['reviewer_tokens'],'output_tokens':limits['output_tokens']})
    if not isinstance(original,dict) or limits_from(original)!=original or any(original[key]!=limits[key] for key in ('dollars','reviewer_tokens','output_tokens')):
        raise ValueError('Saved planning provider allowance is invalid')
    task['limits']=copy.deepcopy(original)
    run=task['branch_run'];run['limits']=limits;run['plan']['limits']=copy.deepcopy(limits)
    if task.get('planning_request',{}).get('measurement') is True:run['plan']['measurement']=True
    else:run['plan'].pop('measurement',None)


def run_limits(values, count):
    defaults = {'dollars':0, 'working_seconds':max(900,count*300), 'worker_turns':count*40,
                'requests':count*60+16, 'tool_actions':count*200, 'reviewer_tokens':max(20000,count*10000),
                'check_seconds':360, 'output_tokens':2048}
    if not isinstance(values,dict) or set(values)-set(defaults):
        raise ValueError('Unknown cumulative run limit')
    defaults.update(values)
    for key, maximum in {'dollars':100,'working_seconds':43200,'worker_turns':10**15,'requests':20000,
                         'tool_actions':100000,'reviewer_tokens':1000000,'check_seconds':1800,'output_tokens':16384}.items():
        value=defaults[key]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not 0 <= value <= maximum or (key!='dollars' and (type(value) is not int or value<1)):
            raise ValueError('Invalid cumulative limit: '+key)
    if defaults['requests'] < count*2+2 or defaults['reviewer_tokens'] < (count+1)*512:
        raise ValueError('Run limits cannot cover the mandatory implementation and review stages')
    return defaults


class BranchController:
    def __init__(self, engine):
        self.engine=engine
        self.proposals=ProposalRegistry()
        self.scopes=CheckScopes(engine.project_test_grants)
        self.planning={}
        self.resume_proposals=ProposalRegistry()
        self.final_proposals=ProposalRegistry()

    def model_policy(self):
        from .access_policy import snapshot
        result = {'execution':copy.deepcopy(self.engine.preferences()['execution']), 'providers':copy.deepcopy(self.engine.config)}
        access = snapshot(self.engine.gateway.settings)
        if access is not None: result['gateway_access'] = access
        return result

    def prepare(self, values, planning_task=None):
        with self.engine.lock:
            plan=state.validate_plan(values.get('plan'))
            plan.setdefault('continue_independent',True)
            plan['limits']=run_limits(plan['limits'],len(plan['items']))
            if any(not item['required_checks'] for item in plan['items']) or not plan['final_checks']:
                raise ValueError('Specify required checks for every item and final integration')
            commands=[]
            from .engine import check_argv
            for spec in [s for item in plan['items'] for s in item['required_checks']]+plan['final_checks']:
                argv=evidence.commands([spec])[0]
                check_argv(shlex.join(argv))
                if argv not in commands: commands.append(argv)
            policy=self.model_policy()
            if policy['execution']['mode']=='manual':
                if not all(policy['providers'].get(r) for r in ('worker','reviewer')):
                    raise ValueError('Choose a worker and an independent reviewer in Models')
                if evidence.model_identity(policy['providers']['worker'])==evidence.model_identity(policy['providers']['reviewer']):
                    raise ValueError('Unattended work requires two distinct named models')
            task_id=planning_task['id'] if planning_task else uuid.uuid4().hex
            if planning_task and planning_task['planning_policy']!=policy_for_saved(policy, planning_task['planning_policy']): raise ValueError('Model policy changed during planning; inspect a fresh proposal')
            previous=(planning_task or {}).get('branch_run',{}).get('workspace_mapping')
            if previous:
                # A scope follow-up reuses the inspected, unstarted snapshot.
                # Never overwrite a private copy or adopt a changed source/base.
                mapping=copy.deepcopy(previous)
                if mapping.get('stage')!='prepared' or (planning_task or {}).get('branch_run',{}).get('authorization'):
                    raise ValueError('Only an unstarted snapshot can be replanned')
                if work.inspect_source(values.get('repository'))!={k:mapping[k] for k in ('source','source_identity','common_identity')} or values.get('base_ref')!=mapping['base_ref']:
                    raise ValueError('Captured source or base changed; submit a new planning request')
                if not work._tip(mapping['source'],mapping['target_ref']):
                    raise ValueError('Integration target must be an existing local branch')
                if work._tip(mapping['source'],mapping['feature_ref']):
                    raise ValueError('Feature branch already exists')
                # Preserve execution branch edits while revising the captured scope.
            else:
                mapping=work.prepare(values.get('repository',''), self.engine.store.root/'tasks'/task_id/'workspace',
                                     values.get('base_ref'),values.get('feature_ref'),values.get('target_ref'),task_id)
            # This private preparation performs no source mutation or execution.
            preparation=self.engine.store.root/'tasks'/task_id/'preparation.json'
            mapping=work.materialize(mapping,lambda m:write_json(preparation,m))
            original=values.get('prompt','')
            if not isinstance(original,str) or len(original)>8000:
                raise ValueError('Use a prompt of up to 8,000 characters')
            inputs=values.get('inputs',{})
            if not isinstance(inputs,dict): raise ValueError('Invalid captured inputs')
            run=state.new_run(plan,original_request=original,inputs=inputs,project={k:mapping[k] for k in ('source','source_identity','common_identity')},
                              base_ref=mapping['base_ref'],base_sha=mapping['base_sha'],target_ref=mapping['target_ref'],feature_ref=mapping['feature_ref'],run_id=task_id)
            run['workspace_mapping']=mapping
            run['model_policy']=policy
            limits=run['limits']
            task=self.engine.create({'repository':mapping['source'],'prompt':original or 'Complete '+str((inputs.get('document') or {}).get('path') or 'the proposed work')+': '+plan['items'][0]['title'], 'conversational':True,
                                     'check_command':shlex.join(commands[0]),'limits':{'dollars':limits['dollars'],'run_minutes':min(720,max(1,(limits['working_seconds']+59)//60)),
                                     'worker_turns':200,'iterations':20,'reviewer_tokens':limits['reviewer_tokens'],'check_seconds':limits['check_seconds'],'output_tokens':limits['output_tokens']}},
                                    snapshot_override=(Workspace(mapping['workspace']),mapping['snapshot']),task_id=task_id)
            task['branch_run']=run
            run['test_policy_version']=1
            if planning_task:
                for key in ('usage','request_metrics','events','worker_turns','tool_actions','requests','created_at','planning_request','planning_limits','planning_policy','planning_assumptions','planning_task_limits','transport_retries','transport_json_routes'):
                    if key in planning_task: task[key]=copy.deepcopy(planning_task[key])
                run['consumption']=copy.deepcopy(planning_task['branch_run']['consumption'])
                if 'budget_ledger' in planning_task['branch_run']:run['budget_ledger']=copy.deepcopy(planning_task['branch_run']['budget_ledger'])
            try:
                scopes=[self.scopes.prepare(task,argv) for argv in commands]
            except (OSError,ValueError) as error:
                run['status']='blocked';run['pause_reason']='missing_setup'
                branch_pause.apply(task,error,cause='missing_setup',stage='planning')
                run['status']='blocked'
                self.engine.store.save(task)
                raise ValueError('Run draft saved; verification setup needs attention: '+str(error)) from error
            run['check_scope']=scopes
            run['authorization_workspace']=copy.deepcopy(mapping)
            state.transition(run,'awaiting_authorization')
            self.engine.store.save(task)
            proposal=self.proposals.prepare(task_id,self.contract(task))
            return {'task_id':task_id,**proposal,'readiness':self.readiness(task),**self.test_disclosure(task)}

    def test_disclosure(self, task):
        from .test_policy import disclosure
        return disclosure(self.engine,task)

    def readiness(self, task):
        from .unattended_setup import inspect
        return inspect(task,task['branch_run']['check_scope'])

    def contract(self, task):
        run=task['branch_run']
        from .branch_completion import authorization_run
        policy = copy.deepcopy(run['model_policy']) if run.get('operator_revision_history') else self.model_policy()
        if run.get('operator_revision_history'):
            from .access_policy import validate_current, effective_settings
            validate_current(policy.get('gateway_access'), effective_settings(task,self.engine.gateway.settings))
        if 'gateway_access' not in run.get('model_policy', {}): policy.pop('gateway_access', None)
        policy = policy_for_saved(policy, run.get('model_policy', {}))
        return contract_builder(authorization_run(run),run['authorization_workspace'],policy,run['check_scope'])

    def authorize(self, task_id, values):
        with self.engine.lock:
            task=self.engine.store.get(task_id);run=state.require_supported(task['branch_run'])
            if set(values)-{'proposal_id','approved','full_suite_approved'}: raise ValueError('Start accepts only the inspected proposal and operator decision')
            runtime=self.engine.runtimes.get(task_id)
            if task.get('planning_request') and not run.get('authorization_ref') and runtime and runtime.thread and runtime.thread.is_alive():
                raise ValueError('Planning is still in progress. Continue in chat until the proposal is ready.')
            if run.get('authorization'):
                self.validate_authority(task,run)
                # A repeated same-proposal action returns the existing run, never starts another worker.
                auth=self.proposals.authorize(task_id,values.get('proposal_id'),values.get('approved'),self.contract(task))
                if auth['id']!=run['authorization']['id']: raise ValueError('A different authorization already owns this run')
                if run['status'] == 'awaiting_authorization':
                    return self._finish_start(task)
                return task
            from .test_policy import approve
            approve(task,values.get('full_suite_approved'))
            mapping=run['workspace_mapping']
            if work.inspect_source(mapping['source'])!={k:mapping[k] for k in ('source','source_identity','common_identity')}:
                raise ValueError('Project changed; prepare a fresh proposal')
            if work._tip(mapping['source'],mapping['base_ref'])!=mapping['base_sha']:
                raise ValueError('Base changed; prepare a fresh proposal')
            work._available(mapping['source'],mapping['feature_ref'],mapping['target_ref'],mapping['protected_refs'])
            if work._tip(mapping['source'],mapping['feature_ref']): raise ValueError('Feature branch now exists')
            for scope in run['check_scope']:
                if self.scopes.prepare(task,scope['command'])!=scope: raise ValueError('Check scope changed; prepare a fresh proposal')
            from .unattended_setup import require_ready
            require_ready(task,run['check_scope'])
            auth=self.proposals.authorize(task_id,values.get('proposal_id'),values.get('approved'),self.contract(task))
            run['authorization']=auth;run['authorization_ref']=auth['id']
            self.engine.store.save(task)
            return self._finish_start(task)

    def _finish_start(self, task):
        """Retry only journaled setup under the same inspected authorization."""
        self.engine.admission.require('unattended', task['id'])
        run=task['branch_run'];self.validate_authority(task,run)
        for scope in run['check_scope']:
            if self.scopes.prepare(task,scope['command'])!=scope:
                raise ValueError('Check scope changed; inspect task setup before continuing')
        from .unattended_setup import require_ready
        require_ready(task,run['check_scope'])
        def save_mapping(value):
            run['workspace_mapping']=value
            self.engine.store.save(task)
        try:
            mapping=work.create(run['workspace_mapping'],save_mapping)
            run['workspace_mapping']=mapping;run['expected_feature_tip']=mapping['feature_tip']
            for scope in run['check_scope']: self.scopes.consent(task,scope)
        except (OSError,ValueError) as error:
            task['error']=branch_pause.classify(error,task,stage='planning')['explanation']
            self.engine.store.save(task)
            raise
        state.transition(run,'running')
        task['status']='running';task['error']=None
        self.engine.store.save(task)
        return self.launch(task['id'])

    def validate_authority(self, task, run):
        self.proposals.validate(run.get('authorization',{}),self.contract(task))
        if run.get('authorization_ref')!=run.get('authorization',{}).get('id'):
            raise ValueError('Run authority reference changed')

    def revoke(self, task_id):
        with self.engine.lock:
            self.engine.admission.require_mutable(task_id)
            task=self.engine.store.get(task_id);run=state.require_supported(task['branch_run'])
            if not run.get('authorization'): raise ValueError('Run is not authorized')
            run['authorization']['status']='revoked'
            runtime=self.engine.runtimes.get(task_id)
            if runtime and runtime.thread and runtime.thread.is_alive():
                runtime.task['branch_run']['authorization']['status']='revoked'
                self.engine.stop(task_id)
                return runtime.task
            run['status']='left_on_branch'; task['status']='completed'
            self.engine.store.save(task)
            return task

    def launch(self, task_id):
        try:return self._launch(task_id)
        except (ValueError,OSError) as error:
            with self.engine.lock:
                task=self.engine.store.get(task_id)
                runtime=self.engine.runtimes.get(task_id)
                if not (runtime and runtime.thread and runtime.thread.is_alive()) and task.get('branch_run',{}).get('status') in {'running','paused','blocked','finalizing'}:
                    branch_pause.apply(task,error)
                    self.engine.store.save(task)
            raise

    def _launch(self, task_id):
        from .engine import Runtime
        import threading
        with self.engine.lock:
            self.engine.require_active_task(task_id)
            self.engine.admission.require('unattended', task_id)
            task=self.engine.store.get(task_id);run=state.require_supported(task['branch_run'])
            # Reconcile exact journaled commits before limits, grants or new work.
            while run['pending_operations']:
                item=next(i for i in run['items'] if i['id']==run['pending_operations'][0]['item_id'])
                self.commit_item(Runtime(task),item)
            self.validate_authority(task,run)
            if run['workspace_mapping']['stage']!='ready':
                def save_mapping(mapping):
                    run['workspace_mapping']=mapping;self.engine.store.save(task)
                run['workspace_mapping']=work.create(run['workspace_mapping'],save_mapping)
                run['expected_feature_tip']=run['workspace_mapping']['feature_tip']
            work.validate_owned(run['workspace_mapping'],run['expected_feature_tip'])
            if run['status'] not in {'paused','blocked','running','finalizing'}:
                raise ValueError('This run is not awaiting execution')
            if run['status'] in {'paused','blocked'}:state.transition(run,'running')
            runtime=Runtime(task)
            runtime.branch_authority=lambda:self.validate_authority(task,run)
            task.pop('operator_continue',None)
            task.update(status='running',route_resume_on_start=False,error=None,error_code=None,stream=None,check_stream=None,pending_approval=None)
            self.engine.store.save(task)
            self.engine.runtimes[task_id]=runtime
            runtime.thread=threading.Thread(target=self.execute,args=(runtime,),daemon=True)
            runtime.thread.start()
            return self.engine.store.get(task_id)

    def commit_item(self, runtime, item):
        from . import branch_commits
        task=runtime.task;run=task['branch_run']
        with self.engine.lock:
            operation=next((op for op in run['pending_operations'] if op['item_id']==item['id']),None)
            if operation is None:
                operation=branch_commits.prepare(task,run,item,item['ready_receipt'],self.validate_authority)
                run['pending_operations'].append(operation)
            def save_operation(value):
                index=next(i for i,op in enumerate(run['pending_operations']) if op['id']==value['id'])
                run['pending_operations'][index]=value
                self.engine.store.save(task)
            receipt=json.loads(operation['receipt'])
            flags={'checks_passed':True,'review_approved':True,'acceptance_satisfied':True,
                   'candidate_id':receipt['candidate']['id'],'review_candidate_id':receipt['candidate']['id'],
                   'worker_model':receipt['worker_model'],'reviewer_model':receipt['reviewer_model'],
                   'no_change':receipt['outcome']=='satisfied_without_change'}
            if not flags['no_change'] and item['status']=='reviewing':state.transition_item(run,item['id'],'committing',flags)
            finished=branch_commits.finish(task,run,item,operation,save_operation,self.validate_authority)
            item['commit_receipt']=copy.deepcopy(finished)
            run['workspace_mapping'].update(feature_tip=finished['new_tip'],workspace_head=finished['private_new'])
            run['expected_feature_tip']=finished['new_tip']
            state.transition_item(run,item['id'],'satisfied_without_change' if flags['no_change'] else 'committed',flags)
            run.setdefault('completed_operations',[]).append(finished)
            run['pending_operations']=[op for op in run['pending_operations'] if op['id']!=finished['id']]
            event=state.append_event(run,'item_completed',{'item_id':item['id'],'title':item['title'],'commit':None if flags['no_change'] else finished['new_tip']},event_key=finished['id'])
            self.engine.refresh_changes(task)
            task.pop('pending_checkpoint',None);task.pop('pending_review',None)
            self.engine.event(task,'branch_commit','Item already satisfied' if flags['no_change'] else 'Committed '+item['title'],event)
            from .model_pool import observe_completions
            observe_completions(self.engine.gateway.pool,task)

    def continue_item(self, runtime, item):
        """Resume the interrupted stage; a pending review is not worker work."""
        task = runtime.task
        if item['status'] == 'reviewing':
            from .branch_review import checkpoint
            saved = task.get('pending_review') or (task.get('operator_review_history') or [{}])[-1]
            self.engine.event(task, 'state', 'Continuing independent review from saved evidence',
                              {'item_id': item['id']})
            result = checkpoint(self.engine, runtime, {
                'summary': saved.get('worker_summary', 'Continuing the interrupted item review.'),
                'uncertainties': saved.get('uncertainties', ''),
                'repair_dispositions': saved.get('repair_dispositions', item.get('review_repair', {}).get('dispositions', []))})
            if result['decision'] != 'REQUEST_CHANGES':
                return
        task['status'] = 'running'
        task['messages'] = self.engine.initial_messages(task)
        self.engine._run_with_wait(runtime)

    def execute(self, runtime):
        runtime.route_autorecover = True
        from .engine import now, OperatorRedirect
        import time
        task=runtime.task;run=task['branch_run']
        metric_id=uuid.uuid4().hex;task['metric_run_id']=metric_id;started=time.monotonic()
        runtime.metric_operator_wait=0;runtime.metric_cooldown_wait=0
        from .branch_budget import Ledger
        runtime.branch_ledger=Ledger(runtime,lambda:self.engine.store.save(task),lock=self.engine.lock)
        try:
            runtime.branch_ledger.begin()
            while True:
                try:
                    if runtime.stop.is_set():raise InterruptedError('Run paused by you')
                    runtime.guard()
                    try:self.validate_authority(task,run)
                    except ValueError as error:raise branch_pause.PauseError('authority_changed') from error
                    # Finish a durable operation before asking any model for more work.
                    if run['pending_operations']:
                        item=next(i for i in run['items'] if i['id']==run['pending_operations'][0]['item_id'])
                        self.commit_item(runtime,item)
                        continue
                    try:work.validate_owned(run['workspace_mapping'],run['expected_feature_tip'])
                    except ValueError as error:raise branch_pause.PauseError('branch_drift') from error
                    from .unattended_items import next_item, defer
                    item=next_item(run)
                    if item is None and any(i['status'] not in state.DONE for i in run['items']):
                        questions=[i.get('question') for i in run['items'] if i.get('question')]
                        run['waiting_for_user']='; '.join(questions) or 'Remaining tasks depend on blocked work.'
                        raise branch_pause.PauseError('essential_clarification')
                    if item is None:
                        if run['status']!='finalizing':state.transition(run,'finalizing')
                        from .branch_completion import finalize
                        if finalize(self.engine,runtime):return
                        continue
                    if item['status'] in {'pending','blocked'}:
                        state.transition_item(run,item['id'],'working')
                        task.update(request_worker_turns=0,iterations=0,active_role='worker',turn_start_patch='',answer_pending=False,action_pending=False)
                        for key in ('loop_guidance','progress_state','pause_summary','recovery_blocked','compact_edits','pending_checkpoint','pending_review','steer_guidance'):
                            task.pop(key,None)
                        runtime.step_turns=0;runtime.argument_failures=0;runtime.observations.clear();runtime.file_observations.clear()
                        runtime.action_context_ready=False;runtime.compact_context_ready=False
                        state.append_event(run,'item_started',{'item_id':item['id'],'title':item['title']})
                        self.engine.event(task,'branch_item','Working on '+item['title'],{'item_id':item['id']})
                    run['current_item_id']=item['id']
                    if item.get('ready_receipt'):
                        try:
                            from .branch_review import context
                            evidence.revalidate(item['ready_receipt'],task,context(run,item),item['required_checks'],item['acceptance_criteria'])
                        except ValueError:item.pop('ready_receipt',None)
                        else:
                            self.commit_item(runtime,item)
                            continue
                    self.continue_item(runtime, item)
                    if run.get('waiting_for_user'):
                        self.engine.refresh_changes(task)
                        clean=not task.get('changes') and not Workspace(task['workspace']).patch(validate=True)
                        if defer(run,item,run['waiting_for_user'],clean):
                            self.engine.event(task,'branch_blocked','Continuing independent work',{'item_id':item['id'],'question':item['question']})
                            self.engine.store.save(task)
                            continue
                        raise branch_pause.PauseError('essential_clarification')
                    if task['status']=='awaiting_reply':
                        # Even an unchanged outcome requires actual criteria review.
                        from .branch_review import checkpoint
                        result=checkpoint(self.engine,runtime,{'summary':'Worker reported the item finished.'})
                        if result['decision']=='REQUEST_CHANGES':
                            task['messages'].append({'role':'user','content':json.dumps(result)})
                            self.engine._run_with_wait(runtime)
                            continue
                    from .branch_worker_recovery import queue as queue_worker_recovery
                    if queue_worker_recovery(self,runtime,item):
                        continue
                    if task['status']=='approved' and item.get('ready_receipt'):
                        self.commit_item(runtime,item)
                        continue
                    raise ValueError(task.get('error') or 'This item needs information or a revised authorization before continuing.')
                except OperatorRedirect:
                    self.engine.apply_operator_direction(runtime)
                    current=next((i for i in run['items'] if i['id']==run.get('current_item_id')),None)
                    if current and current['status'] not in state.DONE:
                        current.setdefault('operator_interruption_history',[]).append({'status':current['status'],'evidence':copy.deepcopy(current.get('evidence',{}))})
                        current['status']='working';current.pop('ready_receipt',None)
                    continue
        except Exception as error:
            if run['status'] not in {'merged','left_on_branch'}:
                error=getattr(runtime,'branch_budget_error',None) or error
                branch_pause.apply(task,error,cause='operator' if runtime.stop.is_set() and not getattr(runtime,'branch_budget_error',None) and not getattr(error,'code',None) and not task.get('error_code') else None)
        finally:
            runtime.branch_ledger.end()
            elapsed=time.monotonic()-started
            provider=sum(r.get('seconds',0) for r in task.get('request_metrics',[]) if r.get('run_id')==metric_id and r.get('dispatched'))
            operator=runtime.metric_operator_wait;cooldown=runtime.metric_cooldown_wait
            task.setdefault('run_metrics',[]).append({'id':metric_id,'elapsed_seconds':elapsed,'provider_request_seconds':provider,'operator_wait_seconds':operator,'provider_cooldown_seconds':cooldown,'controller_work_seconds':max(0,elapsed-provider-operator-cooldown),'outcome':task['status']})
            if len(task['run_metrics'])>500:
                task['run_metrics'].pop(0);task['metrics_history_truncated']=True
            task['metrics_cancelled']=runtime.stop.is_set()
            from .model_pool import observe_task
            observe_task(self.engine.gateway.pool,task,metric_id)
            from .model_pool import observe_completions
            observe_completions(self.engine.gateway.pool,task)
            task['stream']=None;task['check_stream']=None;task['updated_at']=now()
            self.engine.store.save(task)

    def project(self, values):
        source=work.inspect_source(values.get('repository',''))['source']
        refs=work.source_git(source,'for-each-ref','--format=%(refname)','refs/heads').splitlines()
        try:current=work.source_git(source,'symbolic-ref','HEAD')
        except ValueError:current=None
        defaults=[]
        for line in work.source_git(source,'for-each-ref','--format=%(refname) %(symref)','refs/remotes').splitlines():
            parts=line.split()
            if len(parts)==2 and parts[0].endswith('/HEAD'):defaults.append('refs/heads/'+parts[1].split('/',3)[-1])
        target=next((r for r in defaults+['refs/heads/main','refs/heads/master',current] if r in refs),None)
        if not target:raise ValueError('Select a committed local integration target')
        return {'base_ref':target,'target_ref':target,'branches':refs,'current_head':work.source_git(source,'rev-parse','HEAD')}

    def plan(self, values, *, background=False, planning_task=None):
        import threading
        from .engine import Runtime
        from .branch_budget import Ledger
        from .branch_planner import capture_inputs
        identity=values.get('planning_id')
        if not isinstance(identity,str) or not identity or len(identity)>100:raise ValueError('Provide a planning request ID')
        with self.engine.lock:
            if identity in self.planning:raise ValueError('This planning request already exists')
            self.engine.admission.require('unattended', (planning_task or {}).get('id'))
            self.engine.admission.pending[identity]='unattended'
            self.planning[identity]={'runtime':None,'cancelled':False}
        task=None;runtime=None;dispatched=False
        try:
            # Follow-ups use the original captured document, never a silent reread.
            inputs=copy.deepcopy(planning_task['branch_run']['inputs']) if planning_task else capture_inputs(values.get('repository',''),values.get('prompt',''),values.get('document'))
            measurement=values.get('measurement',False)
            if type(measurement) is not bool:raise ValueError('Measurement mode must be a boolean')
            if type(values.get('uncapped_work', False)) is not bool:raise ValueError('Uncapped work must be a boolean')
            limits=planning_task['planning_limits'] if planning_task else run_limits(values.get('limits',{}),3)
            if planning_task:
                task=planning_task
                if task['planning_policy']!=policy_for_saved(self.model_policy(), task['planning_policy']):raise ValueError('Model policy changed; start a new planning chat with the selected models.')
                restore_planning_allowance(task)
                task['branch_run']['status']='draft'
                task['branch_run']['pause_reason']=None
            else:
                task_id=uuid.uuid4().hex;source=inputs['source']
                directory=self.engine.store.root/'tasks'/task_id/'workspace'
                task=self.engine.create({'repository':source,'prompt':inputs['prompt'] or 'Plan work from '+inputs['document']['path'], 'conversational':True,
                                          'limits':{'dollars':limits['dollars'],'run_minutes':max(1,(limits['working_seconds']+59)//60),'reviewer_tokens':limits['reviewer_tokens'],'output_tokens':limits['output_tokens']}},
                                         task_id=task_id,snapshot_override=(Workspace(directory),{'source':source,'files':0,'skipped':[]}))
                task['planning_limits']=limits;task['planning_task_limits']=copy.deepcopy(task['limits']);task['planning_policy']=self.model_policy()
                task['branch_run']=state.new_run({'items':[{'id':'planning','title':'Prepare run proposal','instructions':'Prepare a bounded plan','acceptance_criteria':['A complete proposal is ready']}],'limits':limits,**({'measurement':True} if measurement else {})},original_request=inputs['prompt'],inputs=inputs,
                                                base_ref=values.get('base_ref',''),target_ref=values.get('target_ref',''),feature_ref=values.get('feature_ref',''),run_id=task_id)
            task['planning_request']=copy.deepcopy(values)
            runtime=Runtime(task)
            runtime.branch_ledger=Ledger(runtime,lambda:self.engine.store.save(task),lock=self.engine.lock)
            runtime.thread=threading.Thread(target=self._plan_background,args=(values,runtime,identity),daemon=True,name='cheapos-planner') if background else threading.current_thread()
            with self.engine.lock:
                self.engine.admission.pending.pop(identity, None)
                self.engine.admission.require('unattended', task['id'])
                self.planning[identity]['runtime']=runtime
                self.engine.runtimes[task['id']]=runtime
                if self.planning[identity]['cancelled']:runtime.stop.set()
                task['status']='running';task['error']=None
                self.engine.event(task,'planning','Preparing your Unattended run proposal')
                if background:
                    runtime.thread.start()
                    dispatched=True
                    return {'task_id':task['id']}
            dispatched=True
            return self._finish_plan(values,runtime,identity)
        except Exception as error:
            if not dispatched:
                with self.engine.lock:
                    self.planning.pop(identity,None)
                    self.engine.admission.pending.pop(identity,None)
                    if runtime and self.engine.runtimes.get(task['id']) is runtime:self.engine.runtimes.pop(task['id'],None)
                    if task:
                        task['status']='paused';task['branch_run']['status']='paused';task['error']=str(error)
                        self.engine.event(task,'assistant','Planning needs attention',str(error))
            raise

    def _plan_background(self, values, runtime, identity):
        try:self._finish_plan(values,runtime,identity)
        except Exception:
            import traceback; traceback.print_exc()
            # _finish_plan persists the concrete failure in the conversation.
            # Background exceptions cannot be returned by the kickoff response.
            pass

    def _finish_plan(self, values, runtime, identity):
        from .branch_planner import plan, ClarificationRequired
        task=runtime.task
        try:
            runtime.branch_ledger.begin()
            while True:
                with self.engine.lock:inputs=copy.deepcopy(task['branch_run']['inputs'])
                try:proposed=plan(self.engine,runtime,inputs)
                except ClarificationRequired:
                    with self.engine.lock:
                        if inputs!=task['branch_run']['inputs'] and not runtime.stop.is_set():continue
                    raise
                with self.engine.lock:
                    if runtime.stop.is_set():raise InterruptedError('Planning paused. Reply here when you are ready to continue.')
                    # A reply received during inference supersedes its old scope.
                    if inputs!=task['branch_run']['inputs']:continue
                    if values.get('measurement'):proposed['measurement']=True
                    if values.get('uncapped_work'):proposed['uncapped_work']=True
                    runtime.branch_ledger.end()
                result=self.prepare({**values,'prompt':inputs['prompt'],'inputs':inputs,'plan':proposed},planning_task=task)
                with self.engine.lock:
                    if runtime.stop.is_set() or self.planning[identity]['cancelled']:
                        self.proposals.proposals.pop(result['proposal_id'],None)
                        raise InterruptedError('Planning paused before the proposal was published. Reply here to continue.')
                    if inputs!=task['branch_run']['inputs']:
                        self.proposals.proposals.pop(result['proposal_id'],None)
                        from .branch_budget import Ledger
                        runtime.branch_ledger=Ledger(runtime,lambda:self.engine.store.save(task),lock=self.engine.lock)
                        runtime.branch_ledger.begin()
                        continue
                    saved=self.engine.store.get(task['id'])
                    self.engine.event(saved,'assistant','Proposal ready','The proposal is ready. Inspect it below to review the plan and start the run, or reply here to change it.')
                    self.engine.runtimes.pop(task['id'],None)
                    return result
        except Exception as error:
            if not runtime.branch_ledger.closed.is_set():runtime.branch_ledger.end()
            with self.engine.lock:
                saved=self.engine.store.get(task['id']);saved_run=saved.get('branch_run') or {}
                # Keep a complete plan when verification setup failed in prepare().
                if not (saved_run.get('workspace_mapping') and saved_run.get('status')=='blocked' and saved_run.get('pause_reason')=='missing_setup'):
                    saved=task;saved['status']='paused';saved['branch_run']['status']='paused'
                    branch_pause.apply(saved,error,cause='operator' if runtime.stop.is_set() else 'essential_clarification' if type(error).__name__=='ClarificationRequired' else None,stage='planning')
                saved['stream']=None
                self.engine.event(saved,'assistant','Planning needs attention',str(error) or saved['error'])
                self.engine.runtimes.pop(task['id'],None)
            raise
        finally:
            with self.engine.lock:
                if self.engine.runtimes.get(task['id']) is runtime:self.engine.runtimes.pop(task['id'],None)
                self.planning.pop(identity,None)

    def planning_message(self, task, message):
        from .branch_planner import _digest
        run=task['branch_run']
        if task['planning_policy']!=policy_for_saved(self.model_policy(), task['planning_policy']):raise ValueError('Model policy changed; start a new planning chat with the selected models.')
        messages=run['inputs'].get('followups',[])
        if sum(map(len,messages))+len(message)>24000:raise ValueError('Planning conversation is full; start a new chat.')
        runtime=self.engine.runtimes.get(task['id'])
        active=runtime and runtime.thread and runtime.thread.is_alive()
        if not active:self.engine.admission.require('unattended', task['id'])
        if active and runtime.stop.is_set():raise ValueError('Planning is pausing. Send your reply once it has stopped.')
        run['inputs']['followups']=[*messages,message]
        captured={k:v for k,v in run['inputs'].items() if k!='hash'}
        run['inputs']['hash']=_digest(captured)
        task['requests'].append(message)
        # A changed scope always invalidates every prior Start token.
        with self.proposals.lock:
            self.proposals.proposals={token:p for token,p in self.proposals.proposals.items() if p['task_id']!=task['id']}
        self.engine.event(task,'user','You',message)
        if not active:
            self.plan({**task['planning_request'],'planning_id':uuid.uuid4().hex},background=True,planning_task=task)
        return self.engine.store.get(task['id'])

    def stop_plan(self, values):
        with self.engine.lock:
            record=self.planning.get(values.get('planning_id'))
            if not record:return {'stopped':False}
            record['cancelled']=True
            if record['runtime']:record['runtime'].stop.set()
            return {'stopped':True}

    def resume(self, task_id, values):
        from .engine import Runtime
        with self.engine.lock:
            self.engine.require_active_task(task_id)
            self.engine.admission.require('unattended', task_id)
            task=self.engine.store.get(task_id);run=state.require_supported(task['branch_run'])
            if (run.get('target_update') or {}).get('origin')=='conflict_resolution':
                from .branch_conflicts import complete
                complete(self.engine,task)
            if run.get('target_update'):
                raise ValueError('A branch update is saved. Open Review changes and choose Update branch & recheck to finish it.')
            task.pop('recovery_blocked', None)
            self.engine.store.save(task)
            from .model_pool import observe_completions
            observe_completions(self.engine.gateway.pool,task)
            while run['pending_operations']:
                item=next(i for i in run['items'] if i['id']==run['pending_operations'][0]['item_id'])
                self.commit_item(Runtime(task),item)
            self.validate_authority(task,run)
            if run['workspace_mapping']['stage']=='ready':work.validate_owned(run['workspace_mapping'],run['expected_feature_tip'])
            if run.get('merge_operation'):
                op=run['merge_operation']
                return {'needs_merge_recovery':True,'feature_tip':op['feature_tip'],'target_ref':op['target_ref'],'target_old':op['target_old'],'operation_id':op['id']}
            if run.get('waiting_for_user'):raise ValueError('Send the missing information as guidance in this chat before resuming.')
            commands=[scope['command'] for scope in run['check_scope']]
            scopes=[self.scopes.prepare(task,argv) for argv in commands]
            contract={'authorization_id':run['authorization_ref'],'feature_tip':run['expected_feature_tip'],'scopes':scopes}
            missing=any(not self.scopes.authorize(task,argv) for argv in commands)
            if missing and values.get('approved') is not True:
                proposal=self.resume_proposals.prepare(task_id,contract)
                return {'needs_consent':True,'scopes':scopes,**proposal}
            if missing:
                self.resume_proposals.authorize(task_id,values.get('proposal_id'),values.get('approved'),contract)
                for scope in scopes:self.scopes.consent(task,scope)
            return {'needs_consent':False,'task':self._finish_start(task) if run['status']=='awaiting_authorization' else self.launch(task_id)}

    def proposal(self, task_id):
        with self.engine.lock:
            task=self.engine.store.get(task_id);run=state.require_supported(task['branch_run'])
            if run['status']!='awaiting_authorization' or run.get('authorization'):
                raise ValueError('Only an unstarted proposal can be refreshed')
            return {'task_id':task_id,**self.proposals.prepare(task_id,self.contract(task)),'readiness':self.readiness(task),**self.test_disclosure(task)}

    def message(self, task_id, values):
        message=values.get('message')
        if not isinstance(message,str) or not message.strip() or len(message)>8000:
            raise ValueError('Provide guidance of up to 8,000 characters')
        with self.engine.lock:
            self.engine.require_active_task(task_id)
            runtime=self.engine.runtimes.get(task_id)
            task=runtime.task if runtime and runtime.thread and runtime.thread.is_alive() else self.engine.store.get(task_id)
            run=state.require_supported(task['branch_run'])
            if run.get('target_update'): raise ValueError('Finish the saved branch update: open Review changes, then Update branch & recheck.')
            if task.get('planning_request') and not run.get('authorization_ref'):
                return self.planning_message(task,message.strip())
            if run['status'] not in {'running','paused','blocked'}:
                raise ValueError('Use Request changes to revise completed work')
            self.validate_authority(task,run)
            from .development import enabled
            guidance=run.setdefault('guidance',[])
            if not enabled(task) and sum(len(g['message']) for g in guidance)+len(message)>24000:
                raise ValueError('Guidance is full; prepare an explicit revision')
            guidance.append({'item_id':run['current_item_id'],'message':message.strip()})
            task.pop('recovery_blocked', None)
            answering_blocker=bool(run.pop('waiting_for_user',None))
            if answering_blocker:
                for item in run['items']:
                    if item.get('question'):
                        item.setdefault('clarification_history',[]).append({'question':item.pop('question'),'guidance':message.strip()})
            self.engine.event(task,'user','You',message.strip())
            from .development import enabled
            development=enabled(task)
            active=bool(runtime and runtime.thread and runtime.thread.is_alive())
            self.engine.event(task,'branch_guidance','Guidance saved within the accepted plan',
                              'Applying your correction and continuing within the approved scope.' if development else
                              'Your update is saved for continuation from the current files. The plan and remaining limits are unchanged.' if task['status']=='paused' else 'The worker will receive this on its next turn.')
            if development and active:
                self.engine.queue_operator_direction(runtime,message.strip(),record=False)
                return runtime.task
            if not development:return task
            self.engine.archive_operator_state(task,'Operator corrected paused work')
            self.engine.store.save(task)
        from .branch_operator import continue_saved
        return continue_saved(self,task_id)

    def reprepare(self, task_id, values):
        """Edit an unstarted proposal without renewing its planning allowance.

        The existing committed snapshot is preserved. Switching its repository,
        base or model placement requires a fresh planning request, not a silent
        replacement of this conversation's captured inputs and accounting.
        """
        from .engine import check_argv, limits_from, now
        with self.engine.lock:
            self.engine.require_active_task(task_id)
            task=self.engine.store.get(task_id);old=state.require_supported(task['branch_run'])
            if old['status']!='awaiting_authorization' or old.get('authorization'):
                raise ValueError('Only an unstarted proposal can be edited')
            self.engine.admission.require_idle(task_id)
            allowed={'plan','repository','base_ref','target_ref','feature_ref','prompt','inputs'}
            if not isinstance(values,dict) or set(values)-allowed:
                raise ValueError('Unknown proposal edit field')
            if values.get('prompt',old['original_request'])!=old['original_request'] or values.get('inputs',old['inputs'])!=old['inputs']:
                raise ValueError('Captured prompt/document changed; submit a fresh planning request')
            mapping=copy.deepcopy(old['workspace_mapping'])
            source=work.inspect_source(values.get('repository',mapping['source']))
            if source!={k:mapping[k] for k in ('source','source_identity','common_identity')}:
                raise ValueError('Project changed; submit a fresh planning request')
            if values.get('base_ref',mapping['base_ref'])!=mapping['base_ref'] or work._tip(mapping['source'],mapping['base_ref'])!=mapping['base_sha']:
                raise ValueError('Committed base changed; submit a fresh planning request')
            policy=self.model_policy()
            if policy_for_saved(policy, old['model_policy'])!=old['model_policy']:
                raise ValueError('Model placement changed; submit a fresh planning request')
            plan=state.validate_plan(values.get('plan'))
            plan['limits']=run_limits(plan['limits'],len(plan['items']))
            if any(not item['required_checks'] for item in plan['items']) or not plan['final_checks']:
                raise ValueError('Specify required checks for every item and final integration')
            for key,used in old['consumption'].items():
                if key in plan['limits'] and used>plan['limits'][key]:
                    raise ValueError('Revised limit is below already consumed work: '+key)
            commands=[]
            for spec in [s for item in plan['items'] for s in item['required_checks']]+plan['final_checks']:
                argv=evidence.commands([spec])[0];check_argv(shlex.join(argv))
                if argv not in commands:commands.append(argv)
            mapping['target_ref']=values.get('target_ref',mapping['target_ref'])
            mapping['feature_ref']=values.get('feature_ref',mapping['feature_ref'])
            work._local_ref(mapping['source'],mapping['target_ref'])
            if not work._tip(mapping['source'],mapping['target_ref']):
                raise ValueError('Integration target must be an existing local branch')
            work._available(mapping['source'],mapping['feature_ref'],mapping['target_ref'],mapping['protected_refs'])
            if work._tip(mapping['source'],mapping['feature_ref']):
                raise ValueError('Feature branch already exists')
            # Revalidates original snapshot contents and identities without any
            # source mutation or replacement of the registered private copy.
            mapping=work.materialize(mapping,lambda _:None)
            scopes=[self.scopes.prepare(task,argv) for argv in commands]
            run=state.new_run(plan,original_request=old['original_request'],inputs=old['inputs'],project=old['project'],
                              base_ref=mapping['base_ref'],base_sha=mapping['base_sha'],target_ref=mapping['target_ref'],
                              feature_ref=mapping['feature_ref'],run_id=old['id'])
            for key in ('consumption','budget_ledger','created_at','events','event_sequence'):
                if key in old:run[key]=copy.deepcopy(old[key])
            run.update(plan_revision=old['plan_revision']+1,workspace_mapping=mapping,authorization_workspace=copy.deepcopy(mapping),
                       model_policy=policy,check_scope=scopes)
            state.transition(run,'awaiting_authorization')
            task['branch_run']=run;task['check_command']=commands[0]
            limits=run['limits']
            task['limits']=limits_from({'dollars':limits['dollars'],'run_minutes':min(720,max(1,(limits['working_seconds']+59)//60)),
                                       'worker_turns':200,'iterations':20,'reviewer_tokens':limits['reviewer_tokens'],
                                       'check_seconds':limits['check_seconds'],'output_tokens':limits['output_tokens']})
            task['status']='ready';task['error']=None;task['updated_at']=now()
            # Save the new revision before invalidating old ephemeral tokens. A
            # crash expires every token anyway; no partial edit starts work.
            self.engine.store.save(task)
            with self.proposals.lock:
                self.proposals.proposals={token:proposal for token,proposal in self.proposals.proposals.items() if proposal['task_id']!=task_id}
                proposal=self.proposals.prepare(task_id,self.contract(task))
            return {'task_id':task_id,**proposal,'readiness':self.readiness(task),**self.test_disclosure(task)}
