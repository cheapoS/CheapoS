"""Deterministic conflict task/evidence tests; no model calls or Git fixture costs."""
import copy
import hashlib
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
    def test_clean_files_apply_once_and_preserve_conflicts_and_existing_edits(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                'clean.txt':dict(task='old',suggested='combined'),
                'conflict.txt':dict(task='ours',suggested='<<<<<<< conflict'),
                'edited.txt':dict(task='old',suggested='combined'),
                'added.txt':dict(task=None,suggested='new'),
                'removed.txt':dict(task='old',suggested=None)}
            for name, versions in files.items():
                if versions['task'] is not None:(root/name).write_text(versions['task'])
            (root/'edited.txt').write_text('valuable agent repair')
            context={'files':files,'conflicts':['conflict.txt']}
            resolution={'status':'working','item_id':'resolve','context':context,'context_digest':digest(context)}
            task={'workspace':directory,'active_role':'worker','branch_run':{
                'current_item_id':'resolve','conflict_resolution':resolution,
                'plan':{'items':[{'id':'resolve','instructions':digest(context)}]}}}
            runtime=SimpleNamespace(task=task,guard=Mock())
            engine=SimpleNamespace(refresh_changes=Mock(),event=Mock(),store=SimpleNamespace(save=Mock()))
            with patch('cheapos.branch_disagreement.before_write'):
                conflicts.prepare_clean_files(engine,runtime)
                conflicts.prepare_clean_files(engine,runtime)
            self.assertEqual((root/'clean.txt').read_text(),'combined')
            self.assertEqual((root/'added.txt').read_text(),'new')
            self.assertFalse((root/'removed.txt').exists())
            self.assertEqual((root/'conflict.txt').read_text(),'ours')
            self.assertEqual((root/'edited.txt').read_text(),'valuable agent repair')
            self.assertEqual(engine.store.save.call_count,1)
            self.assertEqual(engine.event.call_args.args[3]['files'],['added.txt','clean.txt','removed.txt'])

    @contextmanager
    def captured_repository(self, skipped=False, extra_files=0):
        # Over 600 KB across versions, including incoming additions/deletions.
        # Git plumbing is stubbed; evidence storage and assignment are real.
        blobs={key:(key+'\n').encode()*40000 for key in ('base','ours','theirs','combined')}
        blobs.update(incoming=b'new target file\n',removed=b'obsolete\n')
        versions={'base':{'a.py':'base','removed.py':'removed'},
                  'old':{'a.py':'ours','removed.py':'removed'},
                  'target':{'a.py':'theirs','incoming.py':'incoming'},
                  'tree':{'a.py':'combined','incoming.py':'incoming'}}
        for number in range(extra_files):
            key=f'extra-{number:04d}';blobs[key]=(key+'\n').encode()
            for version in ('target','tree'):versions[version][key+'.py']=key
        objects={hashlib.sha1(blob).hexdigest():blob for blob in blobs.values()}
        def manifest(source,tip):
            entries=[{'path':name,'oid':hashlib.sha1(blobs[oid]).hexdigest(),'mode':'100755' if name=='incoming.py' else '100644','size':len(blobs[oid])}
                     for name,oid in versions[tip].items() if not skipped or name!='a.py']
            return entries,['a.py'] if skipped else []
        def git(source,*args,**kwargs):
            if args[0]=='status':return ''
            if args[0]=='merge-base':return 'base'
            if args[0]=='diff':return '\0'.join(sorted(set().union(*(v.keys() for v in versions.values())))).encode()+b'\0'
            if args[:2]==('cat-file','--batch'):
                return b''.join((oid+' blob '+str(len(objects[oid]))+'\n').encode()+objects[oid]+b'\n' for oid in kwargs['input'].splitlines())
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

    def test_more_than_100_files_are_captured_in_batches_and_fully_discoverable(self):
        with tempfile.TemporaryDirectory() as directory,self.captured_repository(extra_files=130):
            workspace=Path(directory).resolve()/'workspace';workspace.mkdir()
            context=conflicts.capture({'workspace_mapping':{'source':'source','workspace':str(workspace)},'expected_feature_tip':'old','target_ref':'main'})
            self.assertEqual(len(context['files']),133)
            batches=[call for call in conflicts.work.source_git.call_args_list if call.args[1:3]==('cat-file','--batch')]
            self.assertEqual(len(batches),2)
            task=self.task();run=task['branch_run'];key=digest(context)
            run['conflict_resolution'].update(context=context,context_digest=key)
            run['plan']['items'][0]['instructions']=key
            # The actual worker tool must accept the cursor offered by the schema.
            from types import SimpleNamespace
            from cheapos.engine import Engine,READ_TOOLS
            schema=next(t['function']['parameters'] for t in READ_TOOLS if t['function']['name']=='read_merge_context')
            self.assertIn('file_offset',schema['properties'])
            engine=SimpleNamespace(runtimes={},event=Mock());task.update(id='task',tool_actions=0)
            seen=[];seen_conflicts=[];offset=0
            while offset is not None:
                page=Engine.file_tool(engine,task,'read_merge_context',{'file_offset':offset})
                self.assertEqual(page['file_count'],133)
                self.assertLessEqual(len(page['files']),50)
                seen.extend(page['files']);seen_conflicts.extend(page['conflicts'])
                next_offset=page['next_file_offset']
                if next_offset is not None:self.assertGreater(next_offset,offset)
                offset=next_offset
            self.assertEqual(seen,sorted(context['files']))
            self.assertEqual(seen_conflicts,context['conflicts'])
            self.assertEqual(task['tool_actions'],3)
            for invalid in (-1,True,134):
                with self.assertRaises(ValueError):conflicts.read(task,file_offset=invalid)

    def test_long_lines_page_without_losing_evidence_or_exceeding_read_bound(self):
        from types import SimpleNamespace
        from cheapos.engine import Engine,READ_TOOLS
        schema=next(t['function']['parameters'] for t in READ_TOOLS if t['function']['name']=='read_merge_context')
        self.assertIn('start_column',schema['properties'])
        task=self.task();context=task['branch_run']['conflict_resolution']['context']
        text='Ω'*33000+'\n\nlast line\n'
        context['files']['a.py']['target']=text
        key=digest(context);task['branch_run']['conflict_resolution']['context_digest']=key
        task['branch_run']['plan']['items'][0]['instructions']=key
        task.update(id='task',tool_actions=0);engine=SimpleNamespace(runtimes={},event=Mock())
        line=column=1;received={};pages=0
        while line is not None:
            page=Engine.file_tool(engine,task,'read_merge_context',{'path':'a.py','version':'target','start_line':line,'start_column':column})
            pages+=1;self.assertLessEqual(pages,4)
            self.assertLessEqual(len(page['content']),16000)
            for segment in page['content'].split('\n'):
                number,content=segment.split(': ',1)
                received.setdefault(int(number),[]).append(content)
            next_line,next_column=page['next_line'],page['next_column']
            if next_line is not None:self.assertGreater((next_line,next_column),(line,column))
            line,column=next_line,next_column
        self.assertEqual([''.join(received[n]) for n in sorted(received)],text.splitlines())
        self.assertEqual(pages,3)

    def test_oversized_ranges_continue_and_late_reads_get_a_useful_default(self):
        task=self.task();context=task['branch_run']['conflict_resolution']['context']
        context['files']['a.py']['target']='line\n'*1000
        key=digest(context);task['branch_run']['conflict_resolution']['context_digest']=key
        task['branch_run']['plan']['items'][0]['instructions']=key
        first=conflicts.read(task,'a.py','target',1,10000)
        self.assertEqual(len(first['content'].splitlines()),300)
        self.assertEqual((first['next_line'],first['next_column']),(301,1))
        late=conflicts.read(task,'a.py','target',701)
        self.assertTrue(late['content'].startswith('701: line\n'))
        self.assertEqual(late['next_line'],821)
        for invalid in (-1,0,True,10):
            with self.assertRaises(ValueError):conflicts.read(task,'a.py','target',start_column=invalid)

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
