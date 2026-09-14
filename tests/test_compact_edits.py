from cheapos.routing import PROBE_MARKER
"""Small edits stay bounded, versioned, and recoverable across free workers."""
import copy
import hashlib
import json
import shlex
import sys
from pathlib import Path

from cheapos.engine import COMPACT_GUIDANCE, MAX_CREATE_BYTES, Runtime, check_argv, record_observation
from cheapos.providers import ProviderError
from cheapos.routing import PROBE_MESSAGES
from cheapos.workspace import MAX_EDIT_BYTES, Workspace
from test_engine import LocalCase, call, wait_for
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
        with self.assertRaisesRegex(ValueError, 'edit version does not match'):
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
                    return call('routing_ready', {'marker': PROBE_MARKER}), {'prompt_tokens': 3, 'completion_tokens': 1, 'cost': 0}
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
                                          'new_text': content})
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
                           ('write_file', {'path': 'large.py', 'content': 'x' * (MAX_CREATE_BYTES + 1)})]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.engine.file_tool(task, name, args)
        self.assertTrue(task['compact_edits'])
        self.assertEqual((Path(task['workspace']) / 'math_utils.py').read_bytes(), before)
        self.assertFalse((Path(task['workspace']) / 'large.py').exists())

    def test_complete_new_file_over_chunk_size_is_saved_once(self):
        task=self.chat('remote');task['compact_edits']=True
        content=''.join(f'# Item {i}: a complete generated line\n' for i in range(117))
        self.assertGreater(len(content.encode()),MAX_EDIT_BYTES)
        requests=self.responses([call('write_file',{'path':'report.py','content':content}),
                                 call('ask_user',{'question':'Ready for the next step?'})])
        self.engine.store.save(task);self.engine.start(task['id']);result=self.finish(task)
        path=Path(task['workspace'])/'report.py'
        self.assertEqual(path.read_text(),content)
        self.assertFalse(any(e['kind']=='tool_error' for e in result['events']))
        self.assertEqual(len(requests),2)
        with self.assertRaisesRegex(ValueError,'already exists'):
            self.engine.file_tool(result,'write_file',{'path':'report.py','content':'replacement'})
        self.assertEqual(path.read_text(),content)
        for name,text in [('too_large.py','é'*(MAX_CREATE_BYTES//2+1)),('../outside.py','small')]:
            with self.assertRaises(ValueError):
                self.engine.file_tool(result,'write_file',{'path':name,'content':text})
        self.assertFalse((Path(task['workspace'])/'too_large.py').exists())

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
        path = Path(task['workspace']) / 'math_utils.py'; path.write_text(('line' * 12 + '\n') * 600)
        self.engine.file_tool(task, 'read_file', {'path': 'math_utils.py', 'start_line': 500, 'end_line': 510})
        summary = json.loads(self.engine.action_messages(task)[1]['content'])
        current = summary['current_files'][0]
        self.assertTrue(current['content'].startswith('500: ' + 'line' * 12 + '\n'))
        self.assertFalse(current['complete'])
        path.write_text('changed\n' * 600)
        with self.assertRaisesRegex(ValueError, 'edit version does not match'):
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

    def test_narrow_reads_cannot_shrink_complete_snapshot_or_restore_historical_hashes(self):
        task = self.chat('remote'); task['compact_edits'] = True
        path = Path(task['workspace']) / 'math_utils.py'
        path.write_text('line\n' * 253)
        self.engine.file_tool(task, 'read_file', {'path': 'math_utils.py', 'start_line': 1, 'end_line': 253})
        old_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        path.write_text('current\n' * 253)
        self.engine.file_tool(task, 'read_file', {'path': 'math_utils.py', 'start_line': 1, 'end_line': 20})
        messages = self.engine.action_messages(task)
        current = json.loads(messages[1]['content'])['current_files'][0]
        self.assertTrue(current['complete'])
        self.assertTrue(current['content'].endswith('253: current'))
        self.assertNotIn(old_hash, json.dumps(messages))

    def test_completed_tool_exchange_and_error_feedback_remain_in_next_turn(self):
        task = self.chat('remote'); task['compact_edits'] = True
        self.engine.store.save(task)
        first = call('read_file', {'path': 'math_utils.py'})
        first['content'] = 'I have inspected the function; next I will fix its lower bound.'
        def stale_edit(request):
            (Path(task['workspace']) / 'math_utils.py').write_text('Changed outside the worker\n')
            return call('replace_lines', {'path':'math_utils.py', 'start_line':2,
                                         'end_line':2, 'new_text':'small edit'})
        requests = self.responses([first, stale_edit,
                                  call('ask_user', {'question': 'Which behavior do you want?'})])
        self.engine.start(task['id']); self.finish(task)
        self.assertIn(first, requests[1]['messages'])
        feedback = [m for m in requests[2]['messages'] if m['role'] == 'tool']
        self.assertTrue(any('stale_file_version' in m['content'] for m in feedback))
        self.assertTrue(any('1: Changed outside the worker' in m['content'] for m in feedback))
        self.assertEqual((Path(task['workspace']) / 'math_utils.py').read_text(), 'Changed outside the worker\n')
        self.assertIn(first, requests[2]['messages'])

    def test_controller_versions_sequential_edits_and_ignores_copied_legacy_hash(self):
        task = self.chat('remote'); task['compact_edits'] = True
        self.engine.store.save(task)
        requests = self.responses([
            call('read_file', {'path': './math_utils.py'}),
            call('replace_lines', {'path': 'math_utils.py', 'start_line': 1, 'end_line': 0,
                                  'new_text': '# inserted\n', 'expected_hash': 'badly-copied-hash'}),
            call('replace_lines', {'path': './math_utils.py', 'start_line': 3, 'end_line': 3,
                                  'new_text': '    return max(lower, min(value, upper))\n'}),
            call('ask_user', {'question': 'Ready for your next instruction.'}),
        ])
        self.engine.start(task['id']); result = self.finish(task)
        self.assertFalse(any(e['kind'] == 'tool_error' for e in result['events']))
        self.assertEqual((Path(task['workspace']) / 'math_utils.py').read_text(),
                         '# inserted\ndef clamp(value, lower, upper):\n    return max(lower, min(value, upper))\n')
        for request in requests:
            schema = next(t['function']['parameters'] for t in request['tools'] if t['function']['name'] == 'replace_lines')
            self.assertNotIn('expected_hash', schema['properties'])
        self.assertIn('3:     return min(value, upper)', json.dumps(requests[2]['messages']))
        self.assertEqual(result['review_count'], 0)

    def test_second_edit_in_same_response_cannot_use_shifted_line_numbers(self):
        task = self.chat('remote'); task['compact_edits'] = True
        self.engine.store.save(task)
        batch = call('replace_lines', {'path': 'math_utils.py', 'start_line': 1, 'end_line': 0, 'new_text': '# first\n'})
        second = call('replace_lines', {'path': 'math_utils.py', 'start_line': 2, 'end_line': 2, 'new_text': 'WRONG'})['tool_calls'][0]
        second['id'] = 'call_2'; batch['tool_calls'].append(second)
        requests = self.responses([call('read_file', {'path':'math_utils.py'}), batch,
                                   call('replace_lines', {'path':'math_utils.py', 'start_line':3, 'end_line':3,
                                                         'new_text':'    return max(lower, min(value, upper))\n'}),
                                   call('ask_user', {'question':'Continue?'})])
        self.engine.start(task['id']); result = self.finish(task)
        self.assertEqual((Path(task['workspace']) / 'math_utils.py').read_text(),
                         '# first\ndef clamp(value, lower, upper):\n    return max(lower, min(value, upper))\n')
        errors = [e for e in result['events'] if e['kind'] == 'tool_error']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['detail']['code'], 'same_response_file_mutation')
        self.assertIn('earlier mutation', errors[0]['detail']['error'])
        self.assertIn('3:     return min(value, upper)', json.dumps(requests[2]['messages']))

    def test_unseen_file_edit_is_rejected_and_refreshed_without_user_input(self):
        task = self.chat('remote'); task['compact_edits'] = True
        self.engine.store.save(task)
        requests = self.responses([
            call('replace_lines', {'path':'math_utils.py', 'start_line':1, 'end_line':1, 'new_text':'WRONG'}),
            call('replace_lines', {'path':'math_utils.py', 'start_line':2, 'end_line':2,
                                   'new_text':'    return max(lower, min(value, upper))\n'}),
            call('ask_user', {'question':'Continue?'}),
        ])
        self.engine.start(task['id']); result = self.finish(task)
        self.assertEqual((Path(task['workspace']) / 'math_utils.py').read_text(),
                         'def clamp(value, lower, upper):\n    return max(lower, min(value, upper))\n')
        self.assertIn('stale_file_version', json.dumps(requests[1]['messages']))
        self.assertEqual(sum(e['kind'] == 'tool_error' for e in result['events']), 1)

    def test_new_file_returns_versioned_lines_for_next_chunk(self):
        task = self.chat('remote'); task['compact_edits'] = True
        self.engine.store.save(task)
        requests = self.responses([
            call('write_file', {'path':'new.py', 'content':'# first\n'}),
            call('replace_lines', {'path':'new.py', 'start_line':2, 'end_line':1, 'new_text':'# second\n'}),
            call('ask_user', {'question':'Continue?'}),
        ])
        self.engine.start(task['id']); result = self.finish(task)
        self.assertFalse(any(e['kind'] == 'tool_error' for e in result['events']))
        self.assertEqual((Path(task['workspace']) / 'new.py').read_text(), '# first\n# second\n')
        self.assertIn('1: # first', json.dumps(requests[1]['messages']))

    def test_changing_read_ranges_only_counts_as_progress_when_new_lines_are_returned(self):
        runtime = Runtime(self.chat('remote'))
        def observe(start, end, digest='same'):
            return record_observation(runtime, 'read_file', {'path':'example.py'},
                                      {'hash':digest, 'content':'\n'.join(f'{i}: data' for i in range(start,end+1))})
        self.assertEqual(observe(1, 200), 1)
        self.assertEqual(observe(1, 30), 2)
        self.assertEqual(observe(1, 80), 3)
        self.assertEqual(observe(201, 253), 1)
        self.assertEqual(observe(1, 253), 2)
        self.assertEqual(observe(1, 200, 'edited'), 1)
        self.assertEqual([observe(1, 0, 'empty') for _ in range(3)], [1, 2, 3])

    def test_clipped_snapshot_line_can_be_read_without_a_false_repeat(self):
        task = self.chat('remote'); task['compact_edits'] = True
        path = Path(task['workspace']) / 'math_utils.py'; path.write_text(('x' * 100 + '\n') * 500)
        self.engine.file_tool(task, 'read_file', {'path':'math_utils.py'})
        runtime = Runtime(task)
        snapshot = json.loads(self.engine.compact_context(runtime)[1]['content'])['current_files'][0]
        self.assertTrue(snapshot['truncated'])
        line = int(snapshot['content'].splitlines()[-1].split(':')[0])
        result = Workspace(task['workspace']).read_file('math_utils.py', line, line)
        self.assertEqual(record_observation(runtime,'read_file',{'path':'math_utils.py'},result),1)

    def test_shell_syntax_is_rejected_before_approval_or_execution_and_quoted_data_is_preserved(self):
        task = self.fixture(paid=True); task['conversational'] = True
        runtime = Runtime(task)
        for command in ('python3 -m unittest discover -s tests -v 2>&1 | head -100',
                        'python3 -m unittest > test.log', 'python3 -m unittest && echo done'):
            with self.subTest(command=command), self.assertRaisesRegex(ValueError, 'without shell'):
                self.engine.checks(runtime, command)
        self.assertFalse(task['checks'])
        self.assertIsNone(task.get('pending_approval'))
        self.assertFalse(any(e['kind']=='permission' for e in task['events']))
        task['check_command'] = ['python3', '-m', 'unittest', '2>&1', '|', 'tail', '-50']
        with self.assertRaisesRegex(ValueError, 'saved verification'):
            self.engine.checks(runtime)
        self.assertEqual(check_argv('python3 -c "print(1 > 0)"'), ['python3','-c','print(1 > 0)'])
        self.assertEqual(check_argv('python3 example.py "|"'), ['python3','example.py','|'])

    def test_bad_saved_command_recovers_from_explicit_automatic_and_resumed_checkpoints(self):
        for entry in ('explicit', 'automatic', 'resumed'):
            with self.subTest(entry=entry):
                task = self.chat('remote')
                original_limits = copy.deepcopy(task['limits'])
                bad = ['python3', '-m', 'unittest', '2>&1', '|', 'head', '-30']
                good = [sys.executable, '-m', 'unittest', 'discover', '-v']
                task.update(check_command=bad, auto_approve_checks=True)
                edit = {'path':'math_utils.py', 'old_text':'return min(value, upper)',
                        'new_text':'return max(lower, min(value, upper))'}
                if entry == 'resumed':
                    self.engine.file_tool(task, 'replace_text', edit)
                    task['pending_checkpoint'] = {'summary':'Ready for review.', 'uncertainties':''}
                    task['status'] = 'paused'
                    replies = []
                else:
                    replies = [call('replace_text', edit),
                               call('checkpoint', {'summary':'Ready for review.', 'uncertainties':''})
                               if entry == 'explicit' else {'role':'assistant', 'content':'Finished the change.'}]
                self.engine.store.save(task)
                # Even a legacy session grant cannot authorize malformed argv.
                self.engine.command_permissions[task['id']] = {(task['workspace'], tuple(bad))}
                def correction(request):
                    current = self.engine.store.get(task['id'])
                    self.assertIn('invalid_check_command', json.dumps(request['messages']))
                    self.assertEqual(current['iterations'], 0)
                    self.assertEqual(current['checks'], [])
                    self.assertEqual(current['review_count'], 0)
                    self.assertIsNone(current.get('pending_checkpoint'))
                    return call('run_checks', {'command':shlex.join(good)})
                self.responses(replies + [correction,
                    call('checkpoint', {'summary':'Verified the fix.', 'uncertainties':''}),
                    call('review_decision', {'decision':'APPROVE', 'feedback':'Verified the focused fix.'})])
                self.engine.start(task['id'])
                wait_for(lambda:self.engine.store.get(task['id'])['status'] == 'waiting_approval')
                current = self.engine.store.get(task['id'])
                self.assertEqual(current['pending_approval']['command'], good)
                self.assertEqual(current['checks'], [])
                self.engine.approve_check(task['id'], True)
                result = self.finish(task)
                self.assertEqual(result['status'], 'approved', result['error'])
                self.assertEqual(len(result['checks']), 1)
                self.assertTrue(result['checks'][0]['passed'])
                self.assertEqual(result['checks'][0]['command'], good)
                self.assertEqual(result['iterations'], 1)
                self.assertEqual(result['review_count'], 1)
                self.assertEqual(result['limits'], original_limits)
                self.assertFalse(result.get('commits'))
