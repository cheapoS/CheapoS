import json
import unittest
from pathlib import Path
from cheapos.workspace import git
from test_engine import call
import test_branch_start as fixture


class ScriptedRun:
    def __init__(self):self.steps={};self.revisions=0;self.items=[]
    def complete(self,messages,tools,max_tokens):
        if any(t['function']['name']=='final_review_decision' for t in tools):
            packet=json.loads(messages[1]['content'])
            message=call('final_review_decision',{**{k:packet[k] for k in ('manifest_id','chunk_ids','criteria_ids')},'decision':'APPROVE','feedback':'Passing final suite covers all criteria.'})
        elif any(t['function']['name']=='review_decision' for t in tools):
            packet=json.loads(messages[1]['content']);item=packet['item'];identity=item['id']
            if identity=='two' and not self.revisions:
                self.revisions+=1
                message=call('review_decision',{'decision':'REQUEST_CHANGES','feedback':'Add notes_two.txt explaining the second utility.'})
            else:
                message=call('review_decision',{'decision':'APPROVE','feedback':'Read implementation and passing tests','candidate_id':packet['candidate_id'], 'criteria_outcomes':{c:{'passed':True,'evidence':'Implementation and its actual tests cover this criterion'} for c in item['acceptance_criteria']}})
        else:
            context=json.loads(messages[-1]['content']);item=context['active_item'];identity=item['id'];step=self.steps.get(identity,0);self.steps[identity]=step+1
            if identity not in self.items:self.items.append(identity)
            value={'one':1,'two':2,'three':3}[identity]
            if step==0:message=call('write_file',{'path':identity+'.py','content':'value = '+str(0 if identity=='one' else value)+'\n'})
            elif step==1:message=call('write_file',{'path':'test_'+identity+'.py','content':f'import unittest\nimport {identity}\nclass Check(unittest.TestCase):\n def test_value(self): self.assertEqual({identity}.value,{value})\n'})
            elif identity=='one' and step==3:message=call('replace_text',{'path':'one.py','old_text':'value = 0','new_text':'value = 1'})
            elif identity=='two' and step==3:message=call('write_file',{'path':'notes_two.txt','content':'Second utility returns two.\n'})
            else:message=call('checkpoint',{'summary':'Item implemented','uncertainties':''})
        return message,{'prompt_tokens':10,'completion_tokens':5,'cost':0}


class BranchExecutionTests(unittest.TestCase):
    setUp=fixture.BranchStartTests.setUp
    def run_job(self,limits=None,script=None):
        command=self.values['plan']['final_checks'][0]
        self.values['plan']['items']=[{'id':name,'title':'Utility '+name,'instructions':'Implement '+name,'dependencies':[] if n==0 else [names[n-1]],'acceptance_criteria':['Utility '+name+' works'],'required_checks':[command]} for names in [('one','two','three')] for n,name in enumerate(names)]
        if limits:self.values['plan']['limits'].update(limits)
        self.script=script or ScriptedRun();self.engine.provider_factory=lambda *args:self.script
        proposal=self.engine.branch.prepare(self.values)
        task=self.engine.branch.authorize(proposal['task_id'],{'proposal_id':proposal['proposal_id'],'approved':True})
        self.launch(task['id'])
        runtime=self.engine.runtimes[task['id']];runtime.thread.join(90)
        self.assertFalse(runtime.thread.is_alive())
        return self.engine.store.get(task['id'])

    def test_three_items_repair_review_revision_and_no_intermediate_approval(self):
        task=self.run_job();run=task['branch_run']
        self.assertEqual(run['status'],'ready_for_merge',task.get('error'))
        self.assertEqual([i['status'] for i in run['items']],['committed']*3)
        self.assertEqual(self.script.items,['one','two','three'])
        self.assertEqual(self.script.revisions,1)
        self.assertTrue(any(not c['passed'] for c in task['checks']))
        self.assertEqual(len(run['completed_operations']),3)
        self.assertEqual(git(self.source,'rev-list','--count',run['base_sha']+'..feature/job').strip(),'3')
        self.assertEqual(git(self.source,'status','--porcelain'),'')
        self.assertFalse(any(e['kind']=='permission' and e['title'].startswith('Permission needed') for e in task['events']))
        self.assertGreater(run['consumption']['requests'],0)
        self.assertGreater(run['consumption']['working_seconds'],0)

    def test_outer_turn_limit_stops_without_dropping_items(self):
        task=self.run_job({'worker_turns':2});run=task['branch_run']
        self.assertEqual(run['status'],'paused')
        self.assertEqual(len(run['items']),3)
        self.assertLessEqual(task['worker_turns'],2)
        self.assertEqual(run['pause_reason'],'exhausted_work')

    def test_read_loop_before_first_edit_keeps_implementation_tools(self):
        case=self
        class ReadThenImplement(ScriptedRun):
            reads=0
            def complete(self,messages,tools,max_tokens):
                names={t['function']['name'] for t in tools}
                case.assertTrue(names, 'An accepted implementation must not become a tools-free answer')
                if 'review_decision' not in names and 'final_review_decision' not in names and self.reads<3:
                    self.reads+=1
                    return call('read_file',{'path':'hello.py'}),{'prompt_tokens':10,'completion_tokens':5,'cost':0}
                return super().complete(messages,tools,max_tokens)
        task=self.run_job(script=ReadThenImplement())
        self.assertEqual(task['branch_run']['status'],'ready_for_merge',task.get('error'))
        self.assertEqual([item['status'] for item in task['branch_run']['items']],['committed']*3)
        self.assertTrue(any(e['title']=='Moving from repeated reads to the next action' for e in task['events']))
        self.assertFalse(any(e['title']=='Preparing an answer from gathered evidence' for e in task['events']))
