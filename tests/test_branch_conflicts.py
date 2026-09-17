"""Deterministic conflict task/evidence tests; no model calls or Git fixture costs."""
import copy
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch,Mock
from cheapos import branch_conflicts as conflicts
from cheapos.branch_authorization import digest
from tests import test_branch_operator as fixtures


class ConflictTests(unittest.TestCase):
    @contextmanager
    def captured_repository(self, skipped=False):
        # Over 600 KB across versions, including incoming additions/deletions.
        # Git plumbing is stubbed; evidence storage and assignment are real.
        blobs={key:(key+'\n').encode()*40000 for key in ('base','ours','theirs','combined')}
        blobs.update(incoming=b'new target file\n',removed=b'obsolete\n')
        versions={'base':{'a.py':'base','removed.py':'removed'},
                  'old':{'a.py':'ours','removed.py':'removed'},
                  'target':{'a.py':'theirs','incoming.py':'incoming'},
                  'tree':{'a.py':'combined','incoming.py':'incoming'}}
        def manifest(source,tip):
            entries=[{'path':name,'oid':oid,'mode':'100755' if name=='incoming.py' else '100644','size':len(blobs[oid])}
                     for name,oid in versions[tip].items() if not skipped or name!='a.py']
            return entries,['a.py'] if skipped else []
        def git(source,*args,**kwargs):
            if args[0]=='status':return ''
            if args[0]=='merge-base':return 'base'
            if args[0]=='diff':return b'a.py\0incoming.py\0removed.py\0'
            if args[:2]==('cat-file','blob'):return blobs[args[2]]
            raise AssertionError(args)
        with patch.object(conflicts.work,'validate_owned'),patch.object(conflicts.work,'_tip',return_value='target'),patch.object(conflicts.branch_update,'merge_candidate',return_value=('tree',['a.py'])),patch.object(conflicts.branch_update,'_preserve_exclusions'),patch.object(conflicts.work,'_manifest',side_effect=manifest),patch.object(conflicts.work,'source_git',side_effect=git):
            yield blobs

    def test_large_update_dispatches_and_keeps_frozen_versions_across_reload(self):
        fixture=fixtures.BranchOperatorTests();fixture.setUp()
        with tempfile.TemporaryDirectory() as directory,self.captured_repository() as blobs:
            workspace=Path(directory).resolve()/'workspace';workspace.mkdir()
            fixture.saved['workspace']=str(workspace)
            run=fixture.saved['branch_run'];run['expected_feature_tip']='old';run['target_ref']='refs/heads/main'
            run['workspace_mapping']['workspace']=str(workspace)
            run['items'][0].update(status='committed',commit_receipt={'stage':'completed'})
            contract=conflicts.contract_builder(run,{},run['model_policy'],[])
            proposal=fixture.controller.proposals.prepare('task',contract)
            auth=fixture.controller.proposals.authorize('task',proposal['proposal_id'],True,contract)
            run.update(authorization=auth,authorization_ref=auth['id'])
            with patch('cheapos.branch_completion.update_token',return_value='fresh'):
                conflicts.start(fixture.controller,'task',{'approved':True,'update_token':'fresh'})
            fixture.controller.resume.assert_called_once()
            # Simulate a server reload; no live source files/Git objects needed.
            task=json.loads(json.dumps(fixture.saved));run=task['branch_run']
            context=run['conflict_resolution']['context']
            self.assertLess(len(json.dumps(context)),3000)
            self.assertEqual(len(list((workspace.parent/'merge-evidence').iterdir())),len(blobs))
            self.assertEqual(set(conflicts.read(task)['files']),{'a.py','incoming.py','removed.py'})
            for version,oid in [('base','base'),('task','ours'),('target','theirs'),('suggested','combined')]:
                result=conflicts.read(task,'a.py',version,200,201)
                self.assertEqual(result['content'],f'200: {oid}\n201: {oid}')
                self.assertEqual(result['next_line'],202)
            self.assertFalse(conflicts.read(task,'incoming.py','task')['exists'])
            task['active_role']='worker';run['current_item_id']=run['conflict_resolution']['item_id']
            (workspace/'a.py').write_bytes(blobs['ours'])
            conflicts.apply_version(task,'a.py','suggested')
            self.assertEqual((workspace/'a.py').read_bytes(),blobs['combined'])
            with self.assertRaisesRegex(ValueError,'already has edits'):
                conflicts.apply_version(task,'a.py','target')
            conflicts.apply_version(task,'incoming.py','suggested')
            self.assertEqual((workspace/'incoming.py').read_bytes(),blobs['incoming'])
            self.assertTrue((workspace/'incoming.py').stat().st_mode & 0o111)
            (workspace/'removed.py').write_bytes(blobs['removed'])
            conflicts.apply_version(task,'removed.py','suggested')
            self.assertFalse((workspace/'removed.py').exists())

    def test_missing_or_changed_evidence_never_overwrites_task_files(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory).resolve()/'workspace';workspace.mkdir()
            task=self.task();task['workspace']=str(workspace);task['active_role']='worker'
            run=task['branch_run'];run['workspace_mapping']={'workspace':str(workspace)}
            run['current_item_id']='resolve';run['conflict_resolution']['status']='working'
            context=run['conflict_resolution']['context']
            ref=conflicts.merge_evidence.retain(workspace,b'theirs\n')
            context['files']['a.py']['target']=ref
            key=digest(context);run['conflict_resolution']['context_digest']=key;run['plan']['items'][0]['instructions']=key
            (workspace/'a.py').write_text('ours\n')
            evidence=workspace.parent/'merge-evidence'/ref['sha256']
            evidence.write_bytes(b'tamper\n')  # Same length, different digest.
            for state in ('changed','missing','symlink'):
                if state=='missing':evidence.unlink()
                if state=='symlink':evidence.symlink_to(workspace/'a.py')
                with self.assertRaises(ValueError):conflicts.read(task,'a.py','target')
                with self.assertRaises(ValueError):conflicts.apply_version(task,'a.py','target')
                self.assertEqual((workspace/'a.py').read_text(),'ours\n')
            with self.assertRaises(ValueError):
                conflicts.merge_evidence.read(workspace,{'sha256':'../workspace/a.py','bytes':5})

    def test_unsupported_snapshot_entry_is_not_mistaken_for_deleted_file(self):
        with self.captured_repository(skipped=True):
            with self.assertRaises(conflicts.UnsupportedIntegration) as raised:
                conflicts.capture({'workspace_mapping':{'source':'source'},'expected_feature_tip':'old','target_ref':'refs/heads/main'})
        self.assertEqual(raised.exception.paths,['a.py'])

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
