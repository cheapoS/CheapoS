"""Tiny real-file recovery cases; no Git fixtures, subprocesses, network or waits."""
import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import edit_history, work_policy
from cheapos.edit_recovery import check_state, check_feedback, repair_packet
from cheapos.engine import Engine, WORKER_TOOLS, CHAT_TOOLS, UNATTENDED_TOOLS, REVIEW_TOOLS
from cheapos.workspace import Workspace


class EditHistoryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.ws = Workspace(self.root)
        self.original = 'class Manager:\n    def run(self):\n        return "  hello  "\n'
        (self.root / 'app.py').write_text(self.original)
        self.task = dict(id='unit', workspace=str(self.root), patch='', changes=[], events=[],
                         status='running', active_role='worker', providers={}, tool_actions=0,
                         checks=[], prompt='Normalize the greeting', checkpoints=[], iterations=0,
                         review_count=0, limits={'uncapped_work': True}, check_command=['python3', 'test_app.py'])
        self.engine = Engine.__new__(Engine)
        self.engine.runtimes = {}
        self.engine.lock = threading.RLock()
        self.engine.store = Mock()
        self.engine.verification_argv = Mock()
        def refresh(task):
            task['patch'] = (self.root / 'app.py').read_text()
            task['changes'] = [{'path': 'app.py'}]
        self.engine.refresh_changes = refresh
        self.runtime = SimpleNamespace(task=self.task, guard=Mock(), stop=threading.Event(),
                                       edit_versions={}, observations={}, step_turns=0)

    def edit(self, old, new, path='app.py'):
        return self.engine.file_tool(self.task, 'replace_text', {'path': path, 'old_text': old, 'new_text': new})

    def test_syntax_failure_is_restored_then_valid_repair_finishes_independent_review(self):
        # The failed edit from the incident: only the first line inherits indentation.
        result = self.edit('def run(self):', 'def helper(text):\n    return text.strip()\ndef run(self):')
        self.assertTrue(result['rolled_back'])
        self.assertFalse(result['updated'])
        self.assertEqual((self.root / 'app.py').read_text(), self.original)
        self.assertIn('2:     def run', result['current_file']['content'])
        self.assertNotIn('edit_history', self.task)
        # Scripted worker follows current-file feedback; no operator recovery.
        self.edit('class Manager:', 'def clean(text):\n    return text.strip()\n\nclass Manager:')
        self.edit('return "  hello  "', 'return clean("  hello  ")')
        def check(*args):
            namespace = {}
            exec((self.root / 'app.py').read_text(), namespace)
            self.assertEqual(namespace['Manager']().run(), 'hello')
            record = {'passed': True, 'command': self.task['check_command'],
                      'digest': hashlib.sha256(self.task['patch'].encode()).hexdigest()}
            self.task['checks'].append(record)
            return record
        self.engine.checks = Mock(side_effect=check)
        self.engine.worker_checks(self.runtime, {})
        self.engine.request = Mock(return_value={'tool_calls': [{'id': 'review', 'function': {
            'name': 'review_decision', 'arguments': json.dumps({'decision': 'APPROVE', 'feedback': 'Greeting normalized; method preserved.'})}}]})
        with patch('cheapos.engine.current_evidence', return_value=True), patch('cheapos.engine.reconciliation.ensure_resolved'):
            result = self.engine.checkpoint(self.runtime, {'summary': 'Normalize greeting'})
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertEqual(self.engine.request.call_args.args[-1], 'reviewer')
        self.assertEqual(self.engine.checks.call_count, 1)
        self.assertTrue(self.task['checkpoints'][0]['checks']['passed'])

    def test_repeated_text_mismatch_recovers_with_line_edit_and_independent_review(self):
        from cheapos.engine import Runtime, limits_from
        task = self.task
        task.update(limits=limits_from({'uncapped_work': True}), messages=[], worker_turns=0)
        runtime = Runtime(task)
        engine = self.engine
        engine.fit_worker_context = Mock()
        engine.deliver_loop_guidance = Mock()
        engine.refresh_worker_conversation = Mock()

        def call(name, args, identity):
            return {'role': 'assistant', 'tool_calls': [{'id': identity, 'function': {
                'name': name, 'arguments': json.dumps(args)}}]}
        responses = iter([
            call('replace_text', {'path': 'app.py', 'old_text': 'missing', 'new_text': 'hi'}, 'bad1'),
            call('replace_text', {'path': 'app.py', 'old_text': 'missing', 'new_text': 'hi'}, 'bad2'),
            call('replace_lines', {'path': 'app.py', 'start_line': 3, 'end_line': 3,
                                  'new_text': '        return "hello"\n'}, 'fixed'),
            call('checkpoint', {'summary': 'Normalize greeting', 'uncertainties': ''}, 'done'),
        ])
        def request(rt, messages, tools, role):
            if role == 'reviewer':
                self.assertTrue(task['checks'][-1]['passed'])
                self.assertIn('return "hello"', task['checkpoints'][-1]['diff'])
                return call('review_decision', {'decision': 'APPROVE',
                            'feedback': 'Greeting normalized; Manager.run preserved.'}, 'review')
            return next(responses)
        engine.request = Mock(side_effect=request)
        def check(*args):
            namespace = {}
            exec((self.root / 'app.py').read_text(), namespace)
            self.assertEqual(namespace['Manager']().run(), 'hello')
            result = {'passed': True, 'command': task['check_command'],
                      'digest': hashlib.sha256(task['patch'].encode()).hexdigest()}
            task['checks'].append(result)
            return result
        engine.checks = Mock(side_effect=check)
        with patch('cheapos.engine.automatic', return_value=True) as placement, \
                patch('cheapos.engine.reconciliation.ensure_resolved'), \
                patch('cheapos.integration_preparation.observe'), \
                patch('cheapos.integration_preparation.automatic') as integrate:
            engine._run_until_pause(runtime)
            self.assertEqual(task['status'], 'approved', task.get('error'))
            placement.assert_any_call(task, 'worker')
            integrate.assert_called_once_with(engine, task)
        errors = [json.loads(m['content']) for m in task['messages']
                  if m.get('tool_call_id') in ('bad1', 'bad2')]
        self.assertEqual(len(errors), 2)
        self.assertIn('old_text was not found', errors[0]['error'])
        self.assertIn('current_file', errors[1])
        self.assertTrue(task['compact_edits'])
        self.assertEqual(task['worker_turns'], 4)
        self.assertEqual(task['review_count'], 1)
        self.assertEqual(task['checkpoints'][0]['decision'], 'APPROVE')
        engine.checks.assert_called_once()

    def test_rejected_edit_is_not_reapplied_after_restart_or_credited_as_progress(self):
        args = {'path': 'app.py', 'start_line': 2, 'end_line': 2, 'new_text': 'def run(self):',
                'expected_hash': self.ws.read_file('app.py')['hash']}
        operation = Mock(side_effect=self.ws.replace_lines)
        first = edit_history.apply(self.task, self.ws, 'replace_lines', args, operation)
        self.assertTrue(first['rolled_back'])
        restored = json.loads(json.dumps(self.task))
        second = edit_history.apply(restored, self.ws, 'replace_lines', {**args, 'path': './app.py'}, operation)
        self.assertEqual(operation.call_count, 1)
        self.assertFalse(second['executed'])
        self.assertEqual(second['attempts'], 2)
        self.assertEqual((self.root / 'app.py').read_text(), self.original)
        self.assertNotIn('edit_history', restored)
        self.task['_edit_failures'] = {'app.py': 3}
        no_op = self.edit('hello', 'hello')
        self.assertFalse(no_op['changed'])
        self.assertEqual(self.task['_edit_failures']['app.py'], 3)
        self.engine.file_tool(self.task, 'replace_lines', args)
        self.assertEqual(self.task['_edit_failures']['app.py'], 3)

    def test_cosmetic_edits_do_not_renew_failed_repair_but_code_changes_do(self):
        self.edit('    def run(self):', 'def run(self):')
        self.engine.file_tool(self.task, 'append_text', {'path': 'app.py', 'text': '\n# Fixed now!\n'})
        second = self.edit('    def run(self):', 'def run(self):')
        self.assertEqual(second['attempts'], 2)
        self.edit('hello', 'hi')
        third = self.edit('    def run(self):', 'def run(self):')
        self.assertEqual(third['attempts'], 1)

    def test_uncapped_syntax_loop_consults_coordinator_and_finishes_review(self):
        from cheapos.engine import Runtime, limits_from
        task = self.task
        task.update(limits=limits_from({'uncapped_work': True}), messages=[], worker_turns=0,
                    compact_edits=True,
                    execution={'coordinator_assistance': True, 'coordinator_model': 'fixture'},
                    usage={'cost': 0, 'worker': {'tokens': 100}}, request_metrics=[])
        engine = self.engine
        runtime = Runtime(task)
        runtime.observations['unchanged'] = 2
        runtime.edit_versions['app.py'] = self.ws.read_file('app.py')['hash']
        engine.fit_worker_context = Mock()
        engine.deliver_loop_guidance = Mock()
        engine.refresh_worker_conversation = Mock()
        engine.defer_route = Mock()
        def call(name, args, identity):
            return {'role': 'assistant', 'tool_calls': [{'id': identity, 'function': {
                'name': name, 'arguments': json.dumps(args)}}]}
        bad = {'path': 'app.py', 'start_line': 2, 'end_line': 2, 'new_text': 'def run(self):'}
        responses = iter([call('replace_lines', bad, 'bad1'), call('replace_lines', bad, 'bad2'),
                          call('replace_text', {'path': 'app.py', 'old_text': '  hello  ', 'new_text': 'hello'}, 'fixed'),
                          call('checkpoint', {'summary': 'Normalize greeting', 'uncertainties': ''}, 'done')])
        def request(rt, messages, tools, role, **kwargs):
            if role == 'coordinator':
                self.assertEqual(runtime.observations['unchanged'], 2)
                self.assertEqual((self.root / 'app.py').read_text(), self.original)
                packet = json.loads(messages[1]['content'])
                evidence = next(e for e in packet['evidence'] if e['kind'] == 'rejected_edits')
                self.assertIn('app.py', packet['permitted_paths'])
                self.assertIn('"attempts": 2', evidence['text'])
                return {'content': json.dumps({'outcome': 'continue', 'action': 'edit',
                        'next_step': 'Replace only the greeting text in app.py using replace_text.',
                        'expected_result': 'The greeting is normalized and indentation stays intact.',
                        'evidence': [evidence['id']]})}
            if role == 'reviewer':
                self.assertTrue(task['checks'][-1]['passed'])
                return call('review_decision', {'decision': 'APPROVE', 'feedback': 'Greeting fixed; method preserved.'}, 'review')
            response = next(responses)
            if response['tool_calls'][0]['id'] == 'fixed':
                self.assertIn('replace_text', {t['function']['name'] for t in tools})
                self.assertTrue(any('Internal coordinator recovery guidance' in (m.get('content') or '') for m in messages))
            return response
        engine.request = Mock(side_effect=request)
        def check(*args):
            namespace = {}
            exec((self.root / 'app.py').read_text(), namespace)
            self.assertEqual(namespace['Manager']().run(), 'hello')
            result = {'passed': True, 'command': task['check_command'],
                      'digest': hashlib.sha256(task['patch'].encode()).hexdigest()}
            task['checks'].append(result)
            return result
        engine.checks = Mock(side_effect=check)
        with patch('cheapos.engine.automatic', return_value=True), \
                patch('cheapos.coordinator_recovery.Workspace.list_files', return_value=['app.py']), \
                patch('cheapos.engine.reconciliation.ensure_resolved'), \
                patch('cheapos.integration_preparation.observe'), \
                patch('cheapos.integration_preparation.automatic'):
            engine._run_until_pause(runtime)
        self.assertEqual(task['status'], 'approved', task.get('error'))
        self.assertEqual(task['worker_turns'], 4)
        self.assertEqual(task['review_count'], 1)
        self.assertEqual(len(task['coordinator_recovery']), 1)
        self.assertEqual(task['coordinator_recovery'][0]['state'], 'applied')
        engine.defer_route.assert_not_called()
        self.assertEqual(task['usage']['worker']['tokens'], 100)
        engine.checks.assert_called_once()

    def test_unattended_stall_hands_off_when_help_unavailable_but_preserves_pins_and_gates(self):
        from cheapos.engine import Runtime, limits_from
        task = self.task
        task.update(limits=limits_from({'uncapped_work': True}),
                    branch_run={'id': 'branch', 'current_item_id': '1', 'items': [{'id': '1', 'status': 'working'}],
                                'plan': {'measurement': True}},
                    providers={'worker': {'model': 'first', 'base_url': 'http://gateway.invalid'}},
                    route={'ready': True}, execution={'mode': 'remote'})
        runtime = Runtime(task)
        self.engine.connection_for = Mock(return_value=SimpleNamespace(pool=Mock()))
        with patch('cheapos.coordinator_dispatch.consult', return_value=False) as consult:
            self.assertTrue(self.engine.recover_worker_stall(runtime, 'Repeated rejected edit'))
            self.assertEqual(task['route']['recovery']['worker']['from'], 'first')
            # A queued handoff survives Resume rather than consulting again.
            self.assertTrue(self.engine.recover_worker_stall(runtime, 'Same failure'))
            consult.assert_called_once()
            task['route'].pop('recovery')
            task['operator_worker_model'] = 'first'
            self.assertTrue(self.engine.recover_worker_stall(runtime, 'Repeated rejected edit'))
            self.assertNotIn('recovery', task['route'])
            task['pending_approval'] = {'id': 'permission'}
            self.assertFalse(self.engine.recover_worker_stall(runtime, 'Repeated rejected edit'))
            self.assertEqual(consult.call_count, 2)
        self.assertEqual(task['status'], 'running')
        self.assertEqual(task['checkpoints'], [])
        self.assertEqual(task['limits']['dollars'], 1)

    def test_scope_loss_undo_survives_restart_and_keeps_other_files(self):
        moved = 'def clean(text):\n    return text.strip()\n\n    def run(self):\n        return "  hello  "\n'
        result = self.edit(self.original, moved)
        self.assertEqual(result['structure_changes']['possible_moves'][0]['from'], 'Manager.run')
        self.assertEqual(result['structure_changes']['possible_moves'][0]['to'], 'clean.run')
        (self.root / 'notes.txt').write_bytes(b'keep\r\n')
        self.edit('keep', 'keep this improvement', 'notes.txt')
        self.task = json.loads(json.dumps(self.task))  # Durable receipt, no Runtime dependency.
        rows = self.engine.file_tool(self.task, 'read_edit_history', {'path': './app.py'})
        self.assertTrue(rows['edits'][0]['undo_available'])
        self.assertNotIn('before', rows['edits'][0])
        self.engine.file_tool(self.task, 'undo_edit', {'path': 'app.py', 'edit_id': result['edit_id']})
        namespace = {}; exec((self.root / 'app.py').read_text(), namespace)
        self.assertEqual(namespace['Manager']().run(), '  hello  ')
        self.assertEqual((self.root / 'notes.txt').read_text(), 'keep this improvement\n')

    def test_undo_refuses_newer_same_file_changes_even_if_bytes_match_old_receipt(self):
        first = self.edit('hello', 'hi')
        second = self.edit('hi', 'bye')
        third = self.edit('bye', 'hi')
        for record in (first, second):
            with self.assertRaisesRegex(ValueError, 'Newer changes'):
                self.engine.file_tool(self.task, 'undo_edit', {'path': 'app.py', 'edit_id': record['edit_id']})
        self.engine.file_tool(self.task, 'undo_edit', {'path': 'app.py', 'edit_id': third['edit_id']})
        self.assertIn('bye', (self.root / 'app.py').read_text())
        (self.root / 'app.py').write_text('external edit\n')
        with self.assertRaisesRegex(ValueError, 'Newer changes'):
            self.engine.file_tool(self.task, 'undo_edit', {'path': 'app.py', 'edit_id': second['edit_id']})
        self.assertEqual((self.root / 'app.py').read_text(), 'external edit\n')

    def test_undo_is_bound_to_item_baseline_and_file_permissions(self):
        self.task['branch_run'] = {'id': 'run', 'current_item_id': 'one', 'expected_feature_tip': 'abc'}
        with patch('cheapos.branch_disagreement.before_write') as authority:
            result = self.edit('hello', 'hi')
            self.task['branch_run']['current_item_id'] = 'two'
            with self.assertRaisesRegex(ValueError, 'current task/item'):
                self.engine.file_tool(self.task, 'undo_edit', {'path': 'app.py', 'edit_id': result['edit_id']})
            self.task['branch_run']['current_item_id'] = 'one'
            self.task['branch_run']['expected_feature_tip'] = 'def'
            with self.assertRaisesRegex(ValueError, 'current task/item'):
                self.engine.file_tool(self.task, 'undo_edit', {'path': 'app.py', 'edit_id': result['edit_id']})
            authority.assert_called_with(self.task, 'app.py')
        for path in ('../app.py', '.git/config', '.env'):
            with self.assertRaises(ValueError):
                self.engine.file_tool(self.task, 'undo_edit', {'path': path, 'edit_id': result['edit_id']})
        (self.root / 'link.py').symlink_to(self.root / 'app.py')
        with self.assertRaisesRegex(ValueError, 'Symlinks'):
            self.engine.file_tool(self.task, 'undo_edit', {'path': 'link.py', 'edit_id': result['edit_id']})

    def test_history_bound_noop_and_new_file_undo(self):
        self.edit('hello', 'hello')
        self.assertNotIn('edit_history', self.task)
        for i in range(edit_history.KEEP_EDITS + 2):
            self.edit(str(i-1) if i else 'hello', str(i))
        self.assertEqual(len(self.task['edit_history']), edit_history.KEEP_EDITS)
        result = self.engine.file_tool(self.task, 'write_file', {'path': 'new.py', 'content': 'value = 3\n'})
        self.engine.file_tool(self.task, 'undo_edit', {'path': 'new.py', 'edit_id': result['edit_id']})
        self.assertFalse((self.root / 'new.py').exists())

    def test_rollback_preserves_bytes_mode_and_returns_late_lines(self):
        original = ('# comment\r\n' * 220 + 'def run():\r\n    return 2\r\n').encode()
        (self.root / 'app.py').write_bytes(original)
        (self.root / 'app.py').chmod(0o700)
        result = self.engine.file_tool(self.task, 'replace_lines', {'path': 'app.py', 'start_line': 222,
            'end_line': 222, 'new_text': 'return 3', 'expected_hash': self.ws.read_file('app.py')['hash']})
        self.assertTrue(result['rolled_back'])
        self.assertIn('221: def run', result['current_file']['content'])
        self.assertEqual((self.root / 'app.py').read_bytes(), original)
        self.assertEqual((self.root / 'app.py').stat().st_mode & 0o777, 0o700)

    def test_already_invalid_and_new_chunked_files_can_be_repaired(self):
        result = self.engine.file_tool(self.task, 'write_file', {'path': 'new.py', 'content': 'def foo():\n'})
        self.assertIn('syntax_warning', result)
        result = self.engine.file_tool(self.task, 'append_text', {'path': 'new.py', 'text': '    return 1\n'})
        self.assertNotIn('syntax_warning', result)
        self.assertFalse(result.get('rolled_back'))
        (self.root / 'data.json').write_text('{"value":1}')
        result = self.edit('1', '', 'data.json')
        self.assertTrue(result['rolled_back'])
        self.assertEqual((self.root / 'data.json').read_text(), '{"value":1}')

    def test_structure_shows_fixture_owner_duplicate_and_intentional_move(self):
        before = 'class CorrectTests:\n    def setUp(self): pass\n\nclass OtherTests:\n    pass\n'
        after = before + '    def test_new(self): pass\n    def test_new(self): pass\n'
        info = edit_history.structure(before, after, 'test_app.py')
        self.assertEqual(info['added'][0]['symbol'], 'OtherTests.test_new')
        self.assertEqual(info['new_duplicates'][0]['symbol'], 'OtherTests.test_new')
        info = edit_history.structure(self.original, 'def run(self):\n    return 1\n', 'app.py')
        self.assertIn('Manager.run', info['removed'])
        self.assertIn('Intentional moves are allowed', info['guidance'])

    def test_failed_check_is_historical_after_edit_and_grouped_without_erasing_output(self):
        output = "AttributeError: 'Manager' object has no attribute 'run'\n" * 12 + "AttributeError: 'OtherTests' object has no attribute 'locals'\n" * 4
        self.engine.refresh_changes(self.task)
        check = {'passed': False, 'output': output, 'run_id': 'one',
                 'digest': hashlib.sha256(self.task['patch'].encode()).hexdigest()}
        self.task['checks'].append(check)
        self.assertEqual(check_state(self.task)['state'], 'same_candidate')
        result = self.edit('hello', 'hi')
        self.assertEqual(result['latest_check']['state'], 'predates_current_changes')
        packet = repair_packet(self.task)
        self.assertEqual(packet['latest_check']['failure_groups'][0]['occurrences'], 12)
        self.assertEqual(len(packet['latest_check']['failure_groups']), 2)
        self.assertEqual(check_feedback(check)['output'], output)
        self.assertEqual(check['output'], output)

    def test_undo_offered_only_to_workers_and_honors_same_response_rule(self):
        for tools in (WORKER_TOOLS, CHAT_TOOLS, UNATTENDED_TOOLS):
            self.assertIn('undo_edit', {t['function']['name'] for t in tools})
        self.assertNotIn('undo_edit', {t['function']['name'] for t in REVIEW_TOOLS})
        task = {'conversational': True, 'prompt': work_policy.READ_ONLY_STARTERS[0]}
        self.assertNotIn('undo_edit', {t['function']['name'] for t in work_policy.offered_tools(task, CHAT_TOOLS)})
        result = self.edit('hello', 'hi')
        reply = self.engine.worker_file_tool(self.runtime, 'undo_edit', {'path': './app.py', 'edit_id': result['edit_id']}, {}, {'app.py'})
        self.assertEqual(reply['code'], 'same_response_file_mutation')
        self.assertIn('hi', (self.root / 'app.py').read_text())

    def test_repeated_failure_queues_one_authorized_handoff_instead_of_stopping(self):
        self.engine.checks = Mock(return_value={'passed': False, 'output': 'AttributeError: missing run\n'})
        self.engine.defer_route = Mock()
        self.task['providers']['worker'] = {'model': 'worker-a'}
        with patch('cheapos.engine.automatic', return_value=True):
            for _ in range(7):
                self.engine.worker_checks(self.runtime, {})
        self.engine.defer_route.assert_called_once()
        self.assertEqual(self.task['status'], 'running')
        self.assertIn('undo receipts', self.engine.defer_route.call_args.args[-1])
        # A replacement worker gets its own repair opportunity, without renewing
        # task usage or operator-authorized limits.
        self.task['providers']['worker']['model'] = 'worker-b'
        with patch('cheapos.engine.automatic', return_value=True):
            for _ in range(2):
                result = self.engine.worker_checks(self.runtime, {})
                self.assertFalse(result.get('handoff_queued'))
            result = self.engine.worker_checks(self.runtime, {})
            self.assertTrue(result['handoff_queued'])
        self.assertEqual(self.engine.defer_route.call_count, 2)
        self.assertEqual(self.task['limits'], {'uncapped_work': True})

    def test_receipt_bodies_are_not_in_browser_task_payloads(self):
        from cheapos.server import public_task
        self.edit('hello', 'hi')
        self.assertIn('before', self.task['edit_history'][0])
        self.assertNotIn('edit_history', public_task(self.task))

    def test_fixed_worker_is_not_silently_replaced_after_repeated_failures(self):
        self.engine.checks = Mock(return_value={'passed': False, 'output': 'AttributeError: missing run\n'})
        self.engine.defer_route = Mock()
        self.task.update(execution={'mode': 'remote'}, route={'recovery': {}},
                         operator_worker_model='fixed-worker', providers={'worker': {'model': 'fixed-worker'}})
        for _ in range(7):
            result = self.engine.worker_checks(self.runtime, {})
        self.engine.defer_route.assert_not_called()
        self.assertIn('repair_context', result)
        self.assertEqual(self.task['status'], 'running')
