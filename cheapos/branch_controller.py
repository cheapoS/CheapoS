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


def run_limits(values, count):
    defaults = {'dollars':0, 'working_seconds':max(900,count*300), 'worker_turns':count*40,
                'requests':count*60+16, 'tool_actions':count*200, 'reviewer_tokens':max(20000,count*10000),
                'check_seconds':360, 'output_tokens':2048}
    if not isinstance(values,dict) or set(values)-set(defaults):
        raise ValueError('Unknown cumulative run limit')
    defaults.update(values)
    for key, maximum in {'dollars':100,'working_seconds':43200,'worker_turns':10000,'requests':20000,
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
        return {'execution':copy.deepcopy(self.engine.preferences()['execution']), 'providers':copy.deepcopy(self.engine.config)}

    def prepare(self, values, planning_task=None):
        with self.engine.lock:
            plan=state.validate_plan(values.get('plan'))
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
            if planning_task and planning_task['planning_policy']!=policy: raise ValueError('Model policy changed during planning; inspect a fresh proposal')
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
            if planning_task:
                for key in ('usage','request_metrics','events','worker_turns','tool_actions'):
                    if key in planning_task: task[key]=copy.deepcopy(planning_task[key])
                run['consumption']=copy.deepcopy(planning_task['branch_run']['consumption'])
                if 'budget_ledger' in planning_task['branch_run']:run['budget_ledger']=copy.deepcopy(planning_task['branch_run']['budget_ledger'])
            try:
                scopes=[self.scopes.prepare(task,argv) for argv in commands]
            except (OSError,ValueError) as error:
                run['status']='blocked';run['pause_reason']='missing_setup'
                task['status']='paused';task['error']=str(error)
                self.engine.store.save(task)
                raise ValueError('Run draft saved; verification setup needs attention: '+str(error)) from error
            run['check_scope']=scopes
            run['authorization_workspace']=copy.deepcopy(mapping)
            state.transition(run,'awaiting_authorization')
            self.engine.store.save(task)
            proposal=self.proposals.prepare(task_id,self.contract(task))
            return {'task_id':task_id,**proposal}

    def contract(self, task):
        run=task['branch_run']
        from .branch_completion import authorization_run
        return contract_builder(authorization_run(run),run['authorization_workspace'],self.model_policy(),run['check_scope'])

    def authorize(self, task_id, values):
        with self.engine.lock:
            task=self.engine.store.get(task_id);run=state.require_supported(task['branch_run'])
            if set(values)-{'proposal_id','approved'}: raise ValueError('Start accepts only the inspected proposal and operator decision')
            if run.get('authorization'):
                self.validate_authority(task,run)
                # A repeated same-proposal action returns the existing run, never starts another worker.
                auth=self.proposals.authorize(task_id,values.get('proposal_id'),values.get('approved'),self.contract(task))
                if auth['id']!=run['authorization']['id']: raise ValueError('A different authorization already owns this run')
                return task
            mapping=run['workspace_mapping']
            if work.inspect_source(mapping['source'])!={k:mapping[k] for k in ('source','source_identity','common_identity')}:
                raise ValueError('Project changed; prepare a fresh proposal')
            if work._tip(mapping['source'],mapping['base_ref'])!=mapping['base_sha']:
                raise ValueError('Base changed; prepare a fresh proposal')
            work._available(mapping['source'],mapping['feature_ref'],mapping['target_ref'],mapping['protected_refs'])
            if work._tip(mapping['source'],mapping['feature_ref']): raise ValueError('Feature branch now exists')
            for scope in run['check_scope']:
                if self.scopes.prepare(task,scope['command'])!=scope: raise ValueError('Check scope changed; prepare a fresh proposal')
            auth=self.proposals.authorize(task_id,values.get('proposal_id'),values.get('approved'),self.contract(task))
            run['authorization']=auth;run['authorization_ref']=auth['id']
            self.engine.store.save(task)
            def save_mapping(value):
                run['workspace_mapping']=value
                self.engine.store.save(task)
            mapping=work.create(mapping,save_mapping)
            run['workspace_mapping']=mapping;run['expected_feature_tip']=mapping['feature_tip']
            for scope in run['check_scope']: self.scopes.consent(task,scope)
            state.transition(run,'running')
            task['status']='running';task['error']=None
            self.engine.store.save(task)
            return self.launch(task_id)

    def validate_authority(self, task, run):
        self.proposals.validate(run.get('authorization',{}),self.contract(task))
        if run.get('authorization_ref')!=run.get('authorization',{}).get('id'):
            raise ValueError('Run authority reference changed')

    def revoke(self, task_id):
        with self.engine.lock:
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
        from .engine import Runtime
        import threading
        with self.engine.lock:
            self.engine.require_active_task(task_id)
            if any(r.thread and r.thread.is_alive() for r in self.engine.runtimes.values()):
                raise ValueError('Another task is running. Pause it before starting this run.')
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
            task.update(status='running',error=None,error_code=None,stream=None,check_stream=None,pending_approval=None)
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

    def execute(self, runtime):
        from .engine import now
        import time
        task=runtime.task;run=task['branch_run']
        metric_id=uuid.uuid4().hex;task['metric_run_id']=metric_id;started=time.monotonic()
        runtime.metric_operator_wait=0;runtime.metric_cooldown_wait=0
        from .branch_budget import Ledger
        runtime.branch_ledger=Ledger(runtime,lambda:self.engine.store.save(task),lock=self.engine.lock)
        try:
            runtime.branch_ledger.begin()
            while True:
                if runtime.stop.is_set():raise InterruptedError('Run paused by you')
                runtime.guard()
                self.validate_authority(task,run)
                # Finish a durable operation before asking any model for more work.
                if run['pending_operations']:
                    item=next(i for i in run['items'] if i['id']==run['pending_operations'][0]['item_id'])
                    self.commit_item(runtime,item)
                    continue
                work.validate_owned(run['workspace_mapping'],run['expected_feature_tip'])
                item=next((i for i in run['items'] if i['status'] not in state.DONE),None)
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
                task['status']='running';task['messages']=self.engine.initial_messages(task)
                self.engine._run_with_wait(runtime)
                if run.get('waiting_for_user'): raise ValueError(run['waiting_for_user'])
                if task['status']=='awaiting_reply':
                    # Even an unchanged outcome requires actual criteria review.
                    from .branch_review import checkpoint
                    result=checkpoint(self.engine,runtime,{'summary':'Worker reported the item finished.'})
                    if result['decision']=='REQUEST_CHANGES':
                        task['messages'].append({'role':'user','content':json.dumps(result)})
                        self.engine._run_with_wait(runtime)
                if task['status']=='approved' and item.get('ready_receipt'):
                    self.commit_item(runtime,item)
                    continue
                raise ValueError(task.get('error') or 'This item needs information or a revised authorization before continuing.')
        except Exception as error:
            if run['status'] not in {'merged','left_on_branch'}:
                error=getattr(runtime,'branch_budget_error',None) or error
                reason='exhausted_work' if 'limit' in str(error).lower() else 'operator' if runtime.stop.is_set() else 'branch_drift' if any(word in str(error).lower() for word in ('branch changed','ownership','identity changed')) else 'missing_information'
                run['status']='paused';run['pause_reason']=reason
                task['status']='paused';task['error']=str(error)
                state.append_event(run,'paused',{'reason':reason,'message':str(error)[:1000]})
        finally:
            runtime.branch_ledger.end()
            elapsed=time.monotonic()-started
            provider=sum(r.get('seconds',0) for r in task.get('request_metrics',[]) if r.get('run_id')==metric_id and r.get('dispatched'))
            operator=runtime.metric_operator_wait;cooldown=runtime.metric_cooldown_wait
            task.setdefault('run_metrics',[]).append({'id':metric_id,'elapsed_seconds':elapsed,'provider_request_seconds':provider,'operator_wait_seconds':operator,'provider_cooldown_seconds':cooldown,'controller_work_seconds':max(0,elapsed-provider-operator-cooldown),'outcome':task['status']})
            if len(task['run_metrics'])>500:
                task['run_metrics'].pop(0);task['metrics_history_truncated']=True
            task['metrics_cancelled']=runtime.stop.is_set()
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

    def plan(self, values):
        import threading
        from .engine import Runtime
        from .branch_budget import Ledger
        from .branch_planner import capture_inputs, plan
        identity=values.get('planning_id')
        if not isinstance(identity,str) or not identity or len(identity)>100:raise ValueError('Provide a planning request ID')
        with self.engine.lock:
            if identity in self.planning:raise ValueError('This planning request already exists')
            if any(r.thread and r.thread.is_alive() for r in self.engine.runtimes.values()):raise ValueError('Pause the active task before planning another run')
            self.planning[identity]={'runtime':None,'cancelled':False}
        task=None;runtime=None;prepared=False;ledger_ended=False;registration_error=None
        try:
            inputs=capture_inputs(values.get('repository',''),values.get('prompt',''),values.get('document'))
            limits=run_limits(values.get('limits',{}),3)
            task_id=uuid.uuid4().hex;source=inputs['source']
            directory=self.engine.store.root/'tasks'/task_id/'workspace'
            task=self.engine.create({'repository':source,'prompt':inputs['prompt'] or 'Plan work from '+inputs['document']['path'], 'conversational':True,
                                      'limits':{'dollars':limits['dollars'],'run_minutes':max(1,(limits['working_seconds']+59)//60),'reviewer_tokens':limits['reviewer_tokens'],'output_tokens':limits['output_tokens']}},
                                     task_id=task_id,snapshot_override=(Workspace(directory),{'source':source,'files':0,'skipped':[]}))
            task['planning_limits']=limits;task['planning_policy']=self.model_policy()
            task['branch_run']=state.new_run({'items':[{'id':'planning','title':'Prepare run proposal','instructions':'Prepare a bounded plan','acceptance_criteria':['A complete proposal is ready']}],'limits':limits},original_request=inputs['prompt'],inputs=inputs)
            runtime=Runtime(task);runtime.thread=threading.current_thread()
            runtime.branch_ledger=Ledger(runtime,lambda:self.engine.store.save(task),lock=self.engine.lock)
            with self.engine.lock:
                if any(r.thread and r.thread.is_alive() for r in self.engine.runtimes.values()):
                    registration_error='Another task started while preparing this draft. Pause it, then submit the planning request again.'
                    raise ValueError(registration_error)
                self.planning[identity]['runtime']=runtime
                self.engine.runtimes[task_id]=runtime
                if self.planning[identity]['cancelled']:runtime.stop.set()
            runtime.branch_ledger.begin()
            task['status']='running';self.engine.event(task,'planning','Preparing your Unattended run proposal')
            proposed=plan(self.engine,runtime,inputs)
            if runtime.stop.is_set():raise InterruptedError('Planning cancelled')
            runtime.branch_ledger.end();ledger_ended=True
            with self.engine.lock:self.engine.runtimes.pop(task_id,None)
            if runtime.stop.is_set():raise InterruptedError('Planning cancelled')
            result=self.prepare({**values,'prompt':inputs['prompt'],'inputs':inputs,'plan':proposed},planning_task=task)
            with self.engine.lock:
                if runtime.stop.is_set() or self.planning[identity]['cancelled']:
                    self.proposals.proposals.pop(result['proposal_id'],None)
                    task=self.engine.store.get(task_id)
                    raise InterruptedError('Planning cancelled before proposal publication')
            prepared=True
            return result
        finally:
            if runtime:
                if not ledger_ended:runtime.branch_ledger.end()
                with self.engine.lock:self.engine.runtimes.pop(task['id'],None)
            if task and not prepared:
                task['status']='paused';task['branch_run']['status']='paused';task['branch_run']['pause_reason']='operator' if runtime and runtime.stop.is_set() else 'missing_information'
                task['error']=registration_error or 'Planning stopped or needs clarification; submit an updated request to prepare a proposal.'
                self.engine.store.save(task)
            with self.engine.lock:self.planning.pop(identity,None)

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
            task=self.engine.store.get(task_id);run=state.require_supported(task['branch_run'])
            if any(r.thread and r.thread.is_alive() for r in self.engine.runtimes.values()):raise ValueError('A task is already running')
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
            return {'needs_consent':False,'task':self.launch(task_id)}

    def proposal(self, task_id):
        with self.engine.lock:
            task=self.engine.store.get(task_id);run=state.require_supported(task['branch_run'])
            if run['status']!='awaiting_authorization' or run.get('authorization'):
                raise ValueError('Only an unstarted proposal can be refreshed')
            return {'task_id':task_id,**self.proposals.prepare(task_id,self.contract(task))}

    def message(self, task_id, values):
        message=values.get('message')
        if not isinstance(message,str) or not message.strip() or len(message)>8000:
            raise ValueError('Provide guidance of up to 8,000 characters')
        with self.engine.lock:
            self.engine.require_active_task(task_id)
            runtime=self.engine.runtimes.get(task_id)
            task=runtime.task if runtime and runtime.thread and runtime.thread.is_alive() else self.engine.store.get(task_id)
            run=state.require_supported(task['branch_run'])
            if run['status'] not in {'running','paused','blocked'}:
                raise ValueError('Use Request changes to revise completed work')
            self.validate_authority(task,run)
            guidance=run.setdefault('guidance',[])
            if sum(len(g['message']) for g in guidance)+len(message)>24000:
                raise ValueError('Guidance is full; prepare an explicit revision')
            guidance.append({'item_id':run['current_item_id'],'message':message.strip()})
            run.pop('waiting_for_user',None)
            self.engine.event(task,'user','You',message.strip())
            self.engine.event(task,'branch_guidance','Guidance saved within the accepted plan', 'The plan and remaining limits are unchanged. Resume when ready.' if task['status']=='paused' else 'The worker will receive this on its next turn.')
            return task

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
            if any(r.thread and r.thread.is_alive() for r in self.engine.runtimes.values()):
                raise ValueError('Pause active work before editing a proposal')
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
            if policy!=old['model_policy']:
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
            return {'task_id':task_id,**proposal}
