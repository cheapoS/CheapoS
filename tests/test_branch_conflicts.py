"""Deterministic conflict task/evidence tests; no model calls or Git fixture costs."""
import copy
import unittest
from unittest.mock import patch,Mock
from cheapos import branch_conflicts as conflicts
from cheapos.branch_authorization import digest
from tests import test_branch_operator as fixtures


class ConflictTests(unittest.TestCase):
    def context(self):
        return {'old_tip':'old','target_tip':'target','base_tip':'base','tree':'tree','conflicts':['a.py'],
                'files':{'a.py':{'base':'base\n','task':'ours\n','target':'theirs\n','suggested':'<<<<<<< ours\nours\n=======\ntheirs\n>>>>>>> target\n'}}}

    def task(self):
        context=self.context();key=digest(context)
        return {'branch_run':{'plan':{'items':[{'id':'resolve','instructions':'Context '+key}]},
            'conflict_resolution':{'context':context,'context_digest':key,'item_id':'resolve'}}}

    def test_captured_versions_are_readonly_paged_and_bound_to_plan(self):
        task=self.task();before=copy.deepcopy(task)
        self.assertEqual(conflicts.read(task)['conflicts'],['a.py'])
        self.assertEqual(conflicts.read(task,path='a.py',version='target')['content'],'1: theirs')
        self.assertEqual(task,before)
        for args in ({'path':'../../secret'},{'path':'a.py','version':'live'},{'path':'a.py','start_line':0}):
            with self.assertRaises(ValueError):conflicts.read(task,**args)
        task['branch_run']['conflict_resolution']['context']['target_tip']='changed'
        with self.assertRaises(ValueError):conflicts.read(task)

    def test_stale_or_unapproved_assignment_does_not_capture(self):
        fixture=fixtures.BranchOperatorTests();fixture.setUp()
        fixture.saved['branch_run']['items'][0].update(status='committed',commit_receipt={'stage':'completed'})
        with patch('cheapos.branch_completion.update_token',return_value='fresh'),patch.object(conflicts,'capture') as capture:
            for values in ({'approved':False,'update_token':'fresh'},{'approved':True,'update_token':'stale'}):
                with self.assertRaises(ValueError):conflicts.start(fixture.controller,'task',values)
            capture.assert_not_called()

    def test_resolution_does_not_integrate_unfinished_work(self):
        task=self.task();task['branch_run']['items']=[{'id':'resolve','status':'working'}]
        engine=Mock()
        conflicts.complete(engine,task)
        engine.branch.validate_authority.assert_not_called()

    def test_assignment_preserves_usage_and_creates_authorized_agent_item(self):
        fixture=fixtures.BranchOperatorTests();fixture.setUp()
        fixture.saved['workspace']='private'
        fixture.saved['branch_run']['items'][0].update(status='committed',commit_receipt={'stage':'completed'})
        original=copy.deepcopy(fixture.saved)
        with patch('cheapos.branch_completion.update_token',return_value='fresh'),patch.object(conflicts,'capture',return_value=self.context()),patch.object(conflicts.work,'source_git',return_value=''):
            conflicts.start(fixture.controller,'task',{'approved':True,'update_token':'fresh'})
        task=fixture.saved;run=task['branch_run'];item=run['items'][-1]
        self.assertEqual(item['title'],'Resolve merge conflicts')
        self.assertEqual(item['status'],'pending');self.assertEqual(task['usage'],original['usage'])
        self.assertEqual(item['required_checks'],run['plan']['final_checks'])
        fixture.controller.validate_authority(task,run)
        self.assertEqual(conflicts.read(task)['files'],['a.py'])
        fixture.controller.resume.assert_called_once()

    def test_apply_frozen_version_refuses_overwrite_and_handles_deletion(self):
        import tempfile
        from pathlib import Path
        task=self.task();task.update(active_role='worker')
        run=task['branch_run'];run['current_item_id']='resolve';run['items']=[{'id':'resolve','status':'working'}]
        run['conflict_resolution']['status']='working'
        with tempfile.TemporaryDirectory() as directory:
            task['workspace']=directory;path=Path(directory)/'a.py';path.write_text('ours\n')
            conflicts.apply_version(task,'a.py','target')
            self.assertEqual(path.read_text(),'theirs\n')
            with self.assertRaises(ValueError):conflicts.apply_version(task,'a.py','suggested')
            path.write_text('ours\n')
            context=run['conflict_resolution']['context'];context['files']['a.py']['target']=None
            key=digest(context);run['conflict_resolution']['context_digest']=key;run['plan']['items'][0]['instructions']=key
            conflicts.apply_version(task,'a.py','target')
            self.assertFalse(path.exists())
            with self.assertRaises(ValueError):conflicts.apply_version(task,'../secret','target')

    def test_merge_tools_are_not_advertised_to_ordinary_tasks(self):
        from types import SimpleNamespace
        from cheapos.engine import Engine
        engine=SimpleNamespace(_request_routed=Mock(return_value={}))
        tools=[{'function':{'name':name}} for name in ('read_file','read_merge_context','apply_merge_version')]
        Engine.request(engine,SimpleNamespace(task={}),[],tools,'worker')
        self.assertEqual(engine._request_routed.call_args.args[2],[tools[0]])
