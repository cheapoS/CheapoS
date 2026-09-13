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

    def model_policy(self):
        return {'execution':copy.deepcopy(self.engine.preferences()['execution']), 'providers':copy.deepcopy(self.engine.config)}

    def prepare(self, values):
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
            task_id=uuid.uuid4().hex
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
            # T33 supplies dispatch; no incomplete Start control is exposed in the UI.
            state.transition(run,'paused',reason='missing_setup')
            task['status']='paused';task['error']='Run authorized. Execution controller pending.'
            self.engine.store.save(task)
            return task

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

