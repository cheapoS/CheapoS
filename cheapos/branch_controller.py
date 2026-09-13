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
            task=self.engine.create({'repository':mapping['source'],'prompt':original or 'Complete the selected project document.', 'conversational':True,
                                     'check_command':shlex.join(commands[0]),'limits':{'dollars':limits['dollars'],'run_minutes':min(720,max(1,(limits['working_seconds']+59)//60)),
                                     'worker_turns':200,'iterations':20,'reviewer_tokens':limits['reviewer_tokens'],'check_seconds':limits['check_seconds'],'output_tokens':limits['output_tokens']}},
                                    snapshot_override=(Workspace(mapping['workspace']),mapping['snapshot']),task_id=task_id)
            task['branch_run']=run
            if planning_task:
                for key in ('usage','request_metrics','events','worker_turns','tool_actions'):
                    if key in planning_task: task[key]=copy.deepcopy(planning_task[key])
                run['consumption']=copy.deepcopy(planning_task['branch_run']['consumption'])
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
        return contract_builder(run,run['authorization_workspace'],self.model_policy(),run['check_scope'])

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
        task=runtime.task;run=task['branch_run']
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
                    task['status']='paused';task['error']='Implementation complete; final verification pending.'
                    self.engine.store.save(task)
                    return
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
            task['stream']=None;task['check_stream']=None;task['updated_at']=now()
            self.engine.store.save(task)

