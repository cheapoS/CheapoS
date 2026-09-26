"""Small local search fixtures; no inference, waits or multi-item workflows."""
import base64
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cheapos.workspace import Workspace, FileVersionError, git


class SearchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.workspace = Workspace(self.root)
        # Mock only inventory transport; exercise real filtering, safety and reads.
        self.inventory = []
        mock = patch('cheapos.workspace.git', side_effect=lambda *args: '\0'.join(self.inventory))
        self.git = mock.start()
        self.addCleanup(mock.stop)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode() if isinstance(content, str) else content)
        if name not in self.inventory:
            self.inventory.append(name)
        return path

    def test_more_than_sixty_matches_continue_after_json_restart_without_loss(self):
        self.write('z.py', 'Needle\n' * 70)
        self.write('a.py', 'needle\n' * 65)
        first = self.workspace.search('NEEDLE')
        self.assertEqual(first['returned'], 60)
        self.assertEqual(first['total_matches'], 135)
        self.assertTrue(first['has_more']); self.assertTrue(first['truncated'])
        pages = [first]
        while pages[-1]['has_more']:
            saved = json.loads(json.dumps(pages[-1]))
            pages.append(Workspace(self.root).search('NEEDLE', cursor=saved['next_cursor']))
        actual = [(m['path'], m['line']) for page in pages for m in page['matches']]
        self.assertEqual(actual, [('a.py', n) for n in range(1, 66)] + [('z.py', n) for n in range(1, 71)])
        self.assertIsNone(pages[-1]['next_cursor'])
        self.assertFalse(pages[-1]['truncated'])
        self.assertEqual([p['offset'] for p in pages], [0, 60, 120])

    def test_scope_glob_context_and_long_line_metadata(self):
        self.write('src/a.py', 'before\nneedle\nafter\nlast\n')
        self.write('src/nested/b.py', 'needle\n')
        self.write('src/a.js', 'needle\n')
        self.write('src2/a.py', 'needle\n')
        page = self.workspace.search('needle', path='src', glob='src/*.py', context_lines=1)
        self.assertEqual([m['path'] for m in page['matches']], ['src/a.py', 'src/nested/b.py'])
        match = page['matches'][0]
        self.assertEqual(match['context_before'], [{'line': 1, 'text': 'before', 'text_truncated': False}])
        self.assertEqual(match['context_after'][0]['text'], 'after')
        self.assertEqual(self.workspace.search('needle', path='src/a.js')['total_matches'], 1)
        self.assertEqual(self.workspace.search('needle', glob='*.PY')['matches'], [])
        self.write('long.py', ('é' * 400 + 'needle\n') * 70)
        page = self.workspace.search('needle', path='long.py', context_lines=5)
        self.assertLessEqual(len(json.dumps(page['matches'], ensure_ascii=False)), 20000)
        self.assertLess(page['returned'], 60)
        self.assertTrue(page['matches'][0]['text_truncated'])
        self.assertLessEqual(len(page['matches'][0]['context_after']), 5)
        lines = [m['line'] for m in page['matches']]
        while page['has_more']:
            page = self.workspace.search('needle', path='long.py', context_lines=5, cursor=page['next_cursor'])
            lines.extend(m['line'] for m in page['matches'])
        self.assertEqual(lines, list(range(1, 71)))

    def test_input_validation_before_inventory_or_reads(self):
        bad = [{'query': q} for q in ('', 'a'*201, None, 1, 'a\nb', 'a\rb', '\0')]
        bad += [{'path': p} for p in ('', None, '../x', '/x', 'x/../y', 'x\\y', 'missing', '.env')]
        bad += [{'glob': g} for g in ('', 1, '../*', 'a/../*', '/**', 'a\\*', 'a'*201, '\0')]
        bad += [{'limit': v} for v in (0, 61, -1, True, 1.5, '2', None)]
        bad += [{'context_lines': v} for v in (-1, 6, True, 1.5, None)]
        bad += [{'cursor': c} for c in ('', True, 'not-base64', 'x'*513, 'e30=', 'bnVsbA==')]
        for options in bad:
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.workspace.search(**{'query': 'needle', **options})
        self.git.assert_not_called()

    def test_stale_pages_reject_edits_additions_removals_renames_and_parameter_changes(self):
        source = self.write('a.py', 'needle\n'*70)
        nonmatch = self.write('b.py', 'nothing\n')
        options = {'query': 'needle', 'limit': 2, 'context_lines': 1}
        first = self.workspace.search(**options)
        for changes in ({'query': 'NEEDLE'}, {'limit': 3}, {'context_lines': 0}, {'glob': '*.py'}, {'path': 'a.py'}):
            with self.subTest(changes=changes), self.assertRaises(FileVersionError):
                self.workspace.search(**{**options, **changes}, cursor=first['next_cursor'])
        # Same size and restored mtime still changes the content fingerprint.
        saved = source.stat()
        source.write_text('NEEDLE\n'*70)
        os.utime(source, ns=(saved.st_atime_ns, saved.st_mtime_ns))
        with self.assertRaises(FileVersionError): self.workspace.search(**options, cursor=first['next_cursor'])
        for change in ('nonmatch', 'add', 'remove', 'rename'):
            first = self.workspace.search(**options)
            if change == 'nonmatch': nonmatch.write_text('needle\n')
            elif change == 'add': self.write('c.py', 'needle\n')
            elif change == 'remove': nonmatch.unlink()
            else:
                source.rename(self.root/'d.py'); self.inventory.remove('a.py'); self.inventory.append('d.py')
            with self.subTest(change=change), self.assertRaises(FileVersionError):
                self.workspace.search(**options, cursor=first['next_cursor'])

    def test_changes_outside_scope_do_not_invalidate_cursor(self):
        self.write('src/a.py', 'needle\n'*3)
        other = self.write('other.py', 'nothing')
        page = self.workspace.search('needle', path='src', limit=1)
        other.write_text('needle')
        page = self.workspace.search('needle', path='src', limit=1, cursor=page['next_cursor'])
        self.assertEqual(page['matches'][0]['line'], 2)

    def test_exclusions_symlinks_skip_reporting_and_resource_bounds(self):
        self.write('a.py', 'needle\n')
        for name in ('.env', '.env.local', 'node_modules/a.py', '.git/config', '.ssh/id_rsa', 'key.pem'):
            self.write(name, 'needle')
        (self.root/'link.py').symlink_to(self.root/'a.py'); self.inventory.append('link.py')
        (self.root/'linked').symlink_to(self.root, target_is_directory=True); self.inventory.append('linked/a.py')
        self.write('binary', b'needle\0'); self.write('invalid', b'\xff'); self.write('large', 'x'*101)
        with patch('cheapos.workspace.MAX_FILE_BYTES', 100):
            page = self.workspace.search('needle')
        self.assertEqual([m['path'] for m in page['matches']], ['a.py'])
        self.assertEqual(page['skipped_files'], 3)
        self.assertEqual(page['skip_reasons'], {'non_text_or_oversized': 3})
        for path in ('link.py', 'linked', '.env', 'node_modules'):
            with self.subTest(path=path), self.assertRaises(ValueError): self.workspace.search('needle', path=path)
        with patch('cheapos.workspace.MAX_FILES', 1), self.assertRaisesRegex(ValueError, 'narrow'):
            self.workspace.search('needle')
        with patch('cheapos.workspace.MAX_SNAPSHOT_BYTES', 1), self.assertRaisesRegex(ValueError, 'narrow'):
            self.workspace.search('needle', path='a.py')
        with patch('cheapos.workspace.MAX_FILES', 1):
            self.assertEqual(self.workspace.search('needle', path='a.py')['returned'], 1)

    def test_concurrent_read_change_is_rejected(self):
        source = self.write('a.py', 'needle\n'*3)
        original = self.workspace.text_bytes
        def read(name):
            data = original(name)
            source.write_text('needle changed\n')
            return data
        with patch.object(self.workspace, 'text_bytes', side_effect=read), self.assertRaises(FileVersionError):
            self.workspace.search('needle')

    def test_skipped_file_becoming_text_invalidates_pages_and_concurrent_scan(self):
        self.write('a.py', 'needle\n'*3)
        source = self.write('binary', b'needle\0')
        page = self.workspace.search('needle', limit=1)
        source.write_text('needle\n')
        with self.assertRaises(FileVersionError):
            self.workspace.search('needle', limit=1, cursor=page['next_cursor'])
        source.write_bytes(b'needle\0')
        original = self.workspace.text_bytes
        def read(name):
            if name == 'binary':
                source.write_text('needle\n')
                raise ValueError('Binary files cannot be read by the text tools')
            return original(name)
        with patch.object(self.workspace, 'text_bytes', side_effect=read), self.assertRaises(FileVersionError):
            self.workspace.search('needle')

    def test_cursor_cannot_silently_jump_past_end_or_cross_workspaces(self):
        self.write('a.py', 'needle\n'*3)
        page = self.workspace.search('needle', limit=1)
        cursor = json.loads(base64.urlsafe_b64decode(page['next_cursor']))
        cursor['offset'] = 999
        invalid = base64.urlsafe_b64encode(json.dumps(cursor).encode()).decode()
        with self.assertRaisesRegex(ValueError, 'beyond'): self.workspace.search('needle', limit=1, cursor=invalid)
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'a.py').write_text('needle\n'*3)
            with self.assertRaises(FileVersionError):
                Workspace(directory).search('needle', limit=1, cursor=page['next_cursor'])

    def test_real_git_inventory_preserves_ignore_rules_even_with_explicit_scope(self):
        # One tiny repository; no commits, models, waits or controller workflow.
        with patch('cheapos.workspace.git', wraps=git):
            git(self.root, 'init', '-q')
            self.write('.gitignore', 'build/\n*.ignored\n')
            self.write('build/output.py', 'needle')
            self.write('a.ignored', 'needle')
            self.write('src/a.py', 'needle')
            self.assertEqual(self.workspace.search('needle')['total_matches'], 1)
            self.assertEqual(self.workspace.search('needle', path='build')['total_matches'], 0)
            git(self.root, 'add', '-f', 'a.ignored')
            self.assertEqual(self.workspace.search('needle', glob='*.ignored')['total_matches'], 1)

class SearchRequestTests(unittest.TestCase):
    def test_provider_schema_and_dispatch_survive_correction_resume_and_handoff(self):
        from cheapos import tools, work_policy
        from cheapos.engine import Engine
        from cheapos.instructions.runtime import TOOL_CONTRACT, prompt
        from tests.test_transport import TransportTests
        for profile in ('worker', 'interactive', 'unattended', 'reviewer', 'discussion', 'read_only'):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as directory:
                (Path(directory)/'sample.py').write_text('needle\n'*5)
                app, runtime, _ = TransportTests().harness()
                task = runtime.task
                task.update(workspace=directory, tool_actions=0, active_role='worker',
                            checks=[{'passed': True, 'candidate': 'retained'}],
                            attempt_history=['retained failure'], command_grants=['retained grant'])
                task['limits']['reviewer_tokens'] = 100000
                if profile in ('interactive', 'read_only'): task['conversational'] = True
                if profile == 'unattended': task['branch_run'] = {'authorization_ref': {'id': 'approved'}}
                if profile == 'read_only': task['prompt'] = work_policy.READ_ONLY_STARTERS[0]
                role = 'reviewer' if profile == 'reviewer' else 'worker'
                task['providers'][role] = dict(task['providers']['worker'])
                offered = {'worker': tools.WORKER_TOOLS, 'interactive': tools.CHAT_TOOLS,
                           'unattended': tools.UNATTENDED_TOOLS, 'reviewer': tools.REVIEW_TOOLS,
                           'discussion': [t for t in tools.WORKER_TOOLS if t['function']['name'] in
                                          {'list_files', 'read_file', 'search', 'outline_file'}],
                           'read_only': work_policy.offered_tools(task, tools.CHAT_TOOLS)}[profile]
                messages = [{'role': 'system', 'content': prompt('discussion' if profile == 'discussion'
                            else 'reviewer' if profile == 'reviewer' else 'worker')},
                            {'role': 'user', 'content': 'Find needle in sample.py'}]
                received = []
                args = {'query': 'needle', 'path': 'sample.py', 'glob': '*.py', 'limit': 0, 'context_lines': 1}
                class Provider:
                    def complete(self, sent, available, maximum):
                        received.append((copy.deepcopy(sent), copy.deepcopy(available)))
                        return {'role': 'assistant', 'tool_calls': [{'id': 's'+str(len(received)), 'type': 'function',
                            'function': {'name': 'search', 'arguments': json.dumps(args)}}]}, {
                                'prompt_tokens': 2, 'completion_tokens': 3, 'cost': 0}
                app.provider_factory = lambda *a: Provider()
                found = []
                with patch('cheapos.workspace.git', return_value='sample.py\0'):
                    for phase in ('initial', 'correction', 'resume', 'handoff'):
                        if phase == 'resume':
                            runtime.task = json.loads(json.dumps(runtime.task))
                            messages = json.loads(json.dumps(messages))
                        if phase == 'handoff': runtime.task['providers'][role]['model'] = 'replacement/model'
                        saved = copy.deepcopy(messages)
                        response = app._request_attempt(runtime, messages, offered, role,
                            purpose='chat_reply' if profile == 'discussion' else None)
                        sent, available = received[-1]
                        self.assertEqual(messages, saved)
                        self.assertEqual(sent[0]['content'].count(TOOL_CONTRACT), 1)
                        self.assertIn('partial page, skipped file or clipped text', sent[0]['content'])
                        schemas = {t['function']['name']: t['function'] for t in available}
                        schema = schemas['search']['parameters']
                        self.assertEqual(set(schema['properties']), {'query', 'path', 'glob', 'limit', 'context_lines', 'cursor'})
                        self.assertEqual(schema['required'], ['query'])
                        self.assertFalse(schema['additionalProperties'])
                        self.assertEqual(schema['properties']['limit']['maximum'], 60)
                        self.assertEqual(schema['properties']['context_lines']['maximum'], 5)
                        self.assertIn('next_cursor', schemas['search']['description'])
                        if profile in ('reviewer', 'discussion', 'read_only'):
                            self.assertNotIn('write_file', schemas)
                        calls = [c['id'] for m in sent for c in m.get('tool_calls', [])]
                        replies = [m['tool_call_id'] for m in sent if m['role'] == 'tool']
                        self.assertEqual(calls, replies)
                        call = response['tool_calls'][0]
                        try:
                            result = Engine.file_tool(app, runtime.task, 'search', json.loads(call['function']['arguments']))
                        except ValueError as error:
                            result = {'error': str(error)}
                        messages.extend([response, {'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(result)}])
                        if phase == 'initial':
                            self.assertIn('limit', result['error']); args['limit'] = 2
                        else:
                            found.extend(m['line'] for m in result['matches'])
                            args['cursor'] = result['next_cursor']
                        self.assertEqual(runtime.task['checks'], task['checks'])
                        self.assertEqual(runtime.task['attempt_history'], ['retained failure'])
                        self.assertEqual(runtime.task['command_grants'], ['retained grant'])
                self.assertEqual(found, [1, 2, 3, 4, 5])
                self.assertFalse(result['has_more'])

    def test_item_reviewer_receives_pages_before_separate_validated_decision(self):
        from cheapos import branch_review
        from cheapos.engine import Engine
        from tests.test_branch_disagreement import ReviewCoachingTests
        from tests.test_transport import TransportTests
        from cheapos.instructions.runtime import TOOL_CONTRACT
        task, controller, runtime = ReviewCoachingTests.fixture(self)
        app, transport_runtime, _ = TransportTests().harness()
        transport_runtime.task['providers']['reviewer'] = dict(transport_runtime.task['providers']['worker'])
        transport_runtime.task['limits']['reviewer_tokens'] = 100000
        controller.parse_call = Engine.parse_call
        with tempfile.TemporaryDirectory() as directory:
            task.update(id='task', workspace=directory, tool_actions=0, status='reviewing')
            (Path(directory)/'report.py').write_text('needle\n'*65)
            controller.file_tool.side_effect = lambda t, name, args, **kw: Engine.file_tool(app, t, name, args)
            received = []
            class Provider:
                def complete(provider, messages, tools, maximum):
                    received.append(copy.deepcopy(messages))
                    schemas = {t['function']['name']: t['function'] for t in tools}
                    self.assertIn('cursor', schemas['search']['parameters']['properties'])
                    self.assertEqual(messages[0]['content'].count(TOOL_CONTRACT), 1)
                    receipts = [json.loads(m['content']) for m in messages if m['role'] == 'tool']
                    if not receipts:
                        args = {'query': 'needle', 'path': 'report.py'}
                        name = 'search'
                    elif receipts[-1].get('has_more'):
                        self.assertEqual(receipts[-1]['returned'], 60)
                        args = {'query': 'needle', 'path': 'report.py', 'cursor': receipts[-1]['next_cursor']}
                        name = 'search'
                    else:
                        self.assertEqual(receipts[-1]['returned'], 5)
                        self.assertIsNone(receipts[-1]['next_cursor'])
                        branch_review.evidence.ready_receipt.assert_not_called()
                        args = {'decision': 'APPROVE', 'candidate_id': 'candidate', 'defects': [],
                                'feedback': 'Inspected exact values and supplied checks.',
                                'criteria_outcomes': {'exact values': {'passed': True, 'evidence': 'Source and checks'}}}
                        name = 'review_decision'
                    return {'role': 'assistant', 'tool_calls': [{'id': str(len(received)), 'type': 'function',
                        'function': {'name': name, 'arguments': json.dumps(args)}}]}, {
                            'prompt_tokens': 2, 'completion_tokens': 3, 'cost': 0}
            app.provider_factory = lambda *args: Provider()
            controller.request.side_effect = lambda rt, messages, tools, role, **kw: app._request_attempt(
                transport_runtime, messages, tools, role, **kw)
            with patch('cheapos.workspace.git', return_value='report.py\0'):
                result = branch_review.checkpoint(controller, runtime, {})
            self.assertEqual(result['decision'], 'APPROVE')
            self.assertEqual(len(received), 3)
            self.assertEqual(controller.file_tool.call_count, 2)
            controller.checks.assert_not_called()
            branch_review.evidence.ready_receipt.assert_called_once()
