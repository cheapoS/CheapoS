"""Small edits stay bounded, versioned, and recoverable across free workers."""
import copy
import hashlib
import json
import sys
from pathlib import Path

from cheapos.engine import COMPACT_GUIDANCE
from cheapos.providers import ProviderError
from cheapos.routing import PROBE_MESSAGES
from cheapos.workspace import MAX_EDIT_BYTES, Workspace
from test_engine import LocalCase, call
import test_routing as routing_fixture
from test_routing import model
from test_tool_arguments import malformed


class LineEditTests(LocalCase):
    def workspace(self, data=b'one\r\ntwo\r\nthree\r\n'):
        task = self.fixture()
        workspace = Workspace(task['workspace'])
        workspace.path('lines.txt').write_bytes(data)
        return workspace

    def test_versioned_replacement_insertion_deletion_preserve_other_bytes(self):
        ws = self.workspace()
        read = ws.read_file('lines.txt')
        self.assertEqual(read['content'], '1: one\n2: two\n3: three')
        self.assertEqual(read['hash'], hashlib.sha256(b'one\r\ntwo\r\nthree\r\n').hexdigest())
        edited = ws.replace_lines('lines.txt', 2, 2, 'second', read['hash'])
        self.assertEqual(ws.path('lines.txt').read_bytes(), b'one\r\nsecond\r\nthree\r\n')
        before = ws.path('lines.txt').read_bytes()
        with self.assertRaisesRegex(ValueError, 'changed since inspection'):
            ws.replace_lines('lines.txt', 1, 1, 'stale', read['hash'])
        self.assertEqual(ws.path('lines.txt').read_bytes(), before)
        edited = ws.replace_lines('lines.txt', 2, 1, 'insert\r\n', edited['hash'])
        ws.replace_lines('lines.txt', 3, 3, '', edited['hash'])
        self.assertEqual(ws.path('lines.txt').read_bytes(), b'one\r\ninsert\r\nthree\r\n')

    def test_empty_file_and_unterminated_eof_insertions(self):
        ws = self.workspace(b'')
        edit = ws.replace_lines('lines.txt', 1, 0, 'first', ws.read_file('lines.txt')['hash'])
        ws.replace_lines('lines.txt', 2, 1, 'last', edit['hash'])
        self.assertEqual(ws.path('lines.txt').read_bytes(), b'first\nlast')

    def test_oversized_invalid_and_binary_edits_never_write(self):
        ws = self.workspace(b'line\n' * 100)
        before = ws.path('lines.txt').read_bytes()
        digest = ws.read_file('lines.txt')['hash']
        for start, end, new in [(1, 81, ''), (1, 1, 'x' * (MAX_EDIT_BYTES + 1)),
                                (1, 1, '\u00e9' * 1501), (1, 1, 'x\n' * 81),
                                (0, 1, 'x'), (True, 1, 'x'), (2, 0, 'x'),
                                (1, 101, 'x'), (102, 101, 'x'), (1, 1, '\x00')]:
            with self.subTest(start=start, end=end, length=len(new)), self.assertRaises(ValueError):
                ws.replace_lines('lines.txt', start, end, new, digest)
            self.assertEqual(ws.path('lines.txt').read_bytes(), before)

    def test_path_and_text_boundaries_are_shared_with_reads(self):
        ws = self.workspace()
        outside = self.root / 'outside.txt'; outside.write_text('outside')
        ws.path('link.txt').symlink_to(outside)
        for path in ('../outside.txt', 'link.txt', '.env'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                ws.replace_lines(path, 1, 1, 'changed', 'hash')
        self.assertEqual(outside.read_text(), 'outside')
        for content in (b'x' * 256001, b'\x00binary', b'\xff'):
            ws.path('lines.txt').write_bytes(content)
            with self.assertRaises((ValueError, UnicodeError)):
                ws.replace_lines('lines.txt', 1, 1, 'changed', hashlib.sha256(content).hexdigest())
            self.assertEqual(ws.path('lines.txt').read_bytes(), content)


class CompactRecoveryTests(LocalCase):
    chat = routing_fixture.RoutingTests.chat

    def responses(self, replies):
        self.engine.gateway.catalog.return_value['models'] = [
            model(n, recovery_reasoning={'enabled': False}) for n in ('a', 'b', 'c', 'd')]
        queue, requests = iter(replies), []
        class Provider:
            def __init__(self, role, config): self.role, self.config = role, config
            def complete(self, messages, tools, maximum):
                if messages == PROBE_MESSAGES:
                    return call('routing_ready'), {'prompt_tokens': 3, 'completion_tokens': 1, 'cost': 0}
                request = {'role': self.role, 'config': copy.deepcopy(self.config), 'tools': copy.deepcopy(tools),
                           'messages': copy.deepcopy(messages), 'maximum': maximum}
                requests.append(request)
                reply = next(queue)
                if isinstance(reply, Exception): raise reply
                if callable(reply): reply = reply(request)
                return reply, {'prompt_tokens': 10, 'completion_tokens': 5, 'cost': 0}
        self.engine.provider_factory = lambda role, config: Provider(role, config)
        return requests

    def edit(self, line, content):
        def response(request):
            summary = json.loads(request['messages'][1]['content'])
            file = next(f for f in summary['current_files'] if f['path'] == 'math_utils.py')
            return call('replace_lines', {'path': file['path'], 'start_line': line, 'end_line': line,
                                          'new_text': content, 'expected_hash': file['hash']})
        return response

    def test_malformed_edit_then_success_then_handoff_retains_compact_context_through_review(self):
        task = self.chat('remote')
        task.update(check_command=[sys.executable, '-m', 'unittest', 'discover', '-v'], auto_approve_checks=True)
        self.engine.store.save(task)
        requests = self.responses([
            call('read_file', {'path': 'math_utils.py'}),
            malformed('replace_text', '{"path":"math_utils.py","old_text":"MALFORMED_SENTINEL'),
            self.edit(1, 'def clamp(value, lower, upper):  # bounds'),
            ProviderError('Stream stopped', code='stream_error'),
            self.edit(2, '    return max(lower, min(value, upper))\n'),
            call('checkpoint', {'summary': 'Fixed both bounds.', 'uncertainties': ''}),
            call('review_decision', {'decision': 'APPROVE', 'feedback': 'Checks and bounds verified.'}),
        ])
        self.engine.start(task['id']); result = self.finish(task)
        self.assertEqual(result['status'], 'approved', result['error'])
        self.assertTrue(result['compact_edits'])
        self.assertEqual([r['config']['model'] for r in requests], ['a', 'a', 'a', 'a', 'b', 'b', 'c'])
        for request in requests[2:-1]:
            names = {t['function']['name'] for t in request['tools']}
            self.assertIn('replace_lines', names); self.assertNotIn('replace_text', names)
            self.assertIn('read_file', names)
            self.assertEqual(request['config']['_recovery_reasoning'], {'enabled': False})
            self.assertNotIn('MALFORMED_SENTINEL', json.dumps(request['messages']))
            self.assertEqual(request['maximum'], task['limits']['output_tokens'])
        after_handoff = json.loads(requests[4]['messages'][1]['content'])
        self.assertIn('1: def clamp(value, lower, upper):  # bounds', after_handoff['current_files'][0]['content'])
        self.assertNotIn('replace_lines', {t['function']['name'] for t in requests[-1]['tools']})
        self.assertEqual(result['limits'], task['limits'])
        self.assertEqual(len(result['checks']), 1)
        self.assertFalse(result.get('commits'))
        self.assertEqual((Path(task['source']) / 'math_utils.py').read_text(), 'def clamp(value, lower, upper):\n    return min(value, upper)\n')

    def test_large_valid_edits_are_rejected_before_writing(self):
        task = self.chat('remote')
        before = (Path(task['workspace']) / 'math_utils.py').read_bytes()
        for name, args in [('replace_text', {'path': 'math_utils.py', 'old_text': before.decode(), 'new_text': 'x' * 10000}),
                           ('write_file', {'path': 'large.py', 'content': 'x' * 10000})]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.engine.file_tool(task, name, args)
        self.assertTrue(task['compact_edits'])
        self.assertEqual((Path(task['workspace']) / 'math_utils.py').read_bytes(), before)
        self.assertFalse((Path(task['workspace']) / 'large.py').exists())

    def test_saved_failure_activates_on_resume_and_new_message_resets_mode(self):
        task = self.chat('remote')
        self.responses([{'content': 'Ready.'}]); self.engine.start(task['id']); task = self.finish(task)
        self.engine.file_tool(task, 'read_file', {'path': 'math_utils.py'})
        self.engine.event(task, 'tool_error', 'Bad edit', {'code': 'invalid_tool_arguments', 'tool': 'replace_text'})
        task.update(status='paused', error_code='routing_unavailable', error='Two handoffs tried')
        self.engine.store.save(task)
        requests = self.responses([call('ask_user', {'question': 'Which change next?'})])
        self.engine.start(task['id']); result = self.finish(task)
        self.assertTrue(result['compact_edits'])
        self.assertIn(COMPACT_GUIDANCE, json.dumps(requests[0]['messages']).replace('\\n', '\n'))
        requests = self.responses([{'content': 'The function clamps values.'}])
        self.engine.start(task['id'], {'message': 'Explain the function; do not edit.'}); result = self.finish(task)
        self.assertFalse(result.get('compact_edits'))
        self.assertIn('replace_text', {t['function']['name'] for t in requests[0]['tools']})

    def test_compact_snapshot_keeps_requested_range_and_rejects_stale_hash(self):
        task = self.chat('remote'); task['compact_edits'] = True
        path = Path(task['workspace']) / 'math_utils.py'; path.write_text('line\n' * 600)
        self.engine.file_tool(task, 'read_file', {'path': 'math_utils.py', 'start_line': 500, 'end_line': 510})
        summary = json.loads(self.engine.action_messages(task)[1]['content'])
        current = summary['current_files'][0]
        self.assertTrue(current['content'].startswith('500: line\n'))
        self.assertFalse(current['complete'])
        path.write_text('changed\n' * 600)
        with self.assertRaisesRegex(ValueError, 'changed since inspection'):
            self.engine.file_tool(task, 'replace_lines', {'path': 'math_utils.py', 'start_line': 500,
                                  'end_line': 500, 'new_text': 'stale', 'expected_hash': current['hash']})
        self.assertNotIn('stale', path.read_text())

    def test_compact_malformed_calls_remain_bounded_by_worker_limit(self):
        task = self.chat('remote'); task['limits']['worker_turns'] = 1
        self.engine.store.save(task)
        requests = self.responses([malformed('replace_text')])
        self.engine.start(task['id']); result = self.finish(task)
        self.assertEqual(result['error_code'], 'worker_turn_limit')
        self.assertEqual(len(requests), 1)
        self.assertFalse(result['changes'])
