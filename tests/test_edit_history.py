"""Tiny real-file recovery cases; no Git fixtures, subprocesses, network or waits."""
import hashlib
import io
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
from cheapos.workspace import MAX_EDIT_BYTES, MAX_CREATE_FILE_BYTES, FileEditConstraint, Workspace, edit_size_violation


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

    def test_coherent_rewrite_is_atomic_and_finishes_verification_and_review(self):
        # A complete rewrite used to require several artificial chunks, each
        # individually syntactically valid. Exercise real files without Git.
        old = self.original + '# Existing description\n' * 100
        (self.root / 'app.py').write_text(old)
        replacement = self.original.replace('"  hello  "', '"hello"') + (
            '# Documenting the greeting behavior for operators.\n' * 200)
        args = {'path': 'app.py', 'start_line': 1, 'end_line': len(old.splitlines()),
                'new_text': replacement}
        self.engine.remember_file_version(self.runtime, self.ws.read_file('app.py'))
        # Even recovery guidance must not reject a coherent, complete payload.
        self.engine.prepare_compact_edits(self.task)
        result = self.engine.worker_file_tool(self.runtime, 'replace_lines', args,
                                               dict(self.runtime.edit_versions), set())
        self.assertTrue(result['changed'])
        self.assertEqual((self.root / 'app.py').read_text(), replacement)
        self.assertFalse(self.task.get('compact_edits'))
        self.assertEqual(self.task['tool_actions'], 1)
        self.assertEqual(self.runtime.edit_versions['app.py'], result['current_file']['hash'])
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
            'name': 'review_decision', 'arguments': json.dumps({'decision': 'APPROVE',
                'feedback': 'Complete rewrite preserves the method and normalizes the greeting.'})}}]})
        with patch('cheapos.engine.current_evidence', return_value=True), patch('cheapos.engine.reconciliation.ensure_resolved'):
            decision = self.engine.checkpoint(self.runtime, {'summary': 'Normalize greeting'})
        self.assertEqual(decision['decision'], 'APPROVE')
        self.assertEqual(self.engine.request.call_args.args[-1], 'reviewer')
        self.engine.checks.assert_called_once()

    def test_edit_recovery_survives_rejection_but_ends_after_real_edit(self):
        self.task.update(output_recovery={'worker': True}, checks=[{'passed': False}],
                         session_permissions={'tests': 'granted'}, usage={'cost': 0.01})
        retained = {key: json.loads(json.dumps(self.task[key]))
                    for key in ('limits', 'checks', 'session_permissions', 'usage', 'output_recovery')}
        self.engine.prepare_compact_edits(self.task)
        self.engine.remember_file_version(self.runtime, self.ws.read_file('app.py'))
        args = {'path': 'app.py', 'start_line': 2, 'end_line': 3, 'new_text': '    def run(self):'}
        rejected = self.engine.worker_file_tool(self.runtime, 'replace_lines', args,
                                                 dict(self.runtime.edit_versions), set())
        self.assertTrue(rejected['rolled_back'])
        self.assertTrue(self.task['compact_edits'])
        restored = json.loads(json.dumps(self.task))
        self.assertFalse(work_policy.refresh_edit_recovery(restored))
        self.assertTrue(restored['compact_edits'])
        result = self.engine.worker_file_tool(self.runtime, 'replace_text', {
            'path': 'app.py', 'old_text': '"  hello  "', 'new_text': '"hello"'},
            dict(self.runtime.edit_versions), set())
        self.assertTrue(result['changed'])
        self.assertFalse(self.task.get('compact_edits'))
        for key, value in retained.items():
            self.assertEqual(self.task[key], value)

    def test_edit_guidance_expires_on_worker_item_or_request_change(self):
        self.task.update(providers={'worker': {'model': 'worker', 'base_url': 'local'}},
                         branch_run={'current_item_id': 'item1'}, requests=['Fix greeting'],
                         output_recovery={'worker': True})
        work_policy.begin_edit_recovery(self.task)
        self.task['output_retry'] = {'scope': work_policy.edit_recovery_scope(self.task)}
        for change in ('model', 'base_url', 'item', 'request', 'legacy'):
            with self.subTest(change=change):
                restored = json.loads(json.dumps(self.task))
                if change in ('model', 'base_url'):
                    restored['providers']['worker'][change] = 'new'
                elif change == 'item':
                    restored['branch_run']['current_item_id'] = 'item2'
                elif change == 'request':
                    restored['requests'].append('Next task')
                else:
                    restored.pop('compact_edit_recovery')
                    restored.pop('output_retry')
                self.assertTrue(work_policy.refresh_edit_recovery(restored))
                self.assertFalse(restored.get('compact_edits'))
                self.assertFalse(restored.get('output_retry'))
                self.assertEqual(restored['output_recovery'], {'worker': True})
                self.assertEqual(restored['limits'], self.task['limits'])

    def test_reproduction_and_existing_file_recovery_finish_independent_branch_review(self):
        from contextlib import ExitStack
        from cheapos import branch_disagreement, branch_review, branch_runs
        from cheapos.engine import Runtime, limits_from
        test_text = ('import unittest\nclass GreetingTests(unittest.TestCase):\n'
                     '    def test_existing(self):\n        self.assertIsInstance(Manager().run(), str)\n')
        (self.root / 'test_app.py').write_text(test_text)
        command = ['python3', '-m', 'unittest', 'test_app', '-v']
        run = branch_runs.new_run({'items': [{'id': 'greeting', 'title': 'Normalize greeting',
            'instructions': 'Strip surrounding whitespace in app.py', 'acceptance_criteria': ['Normalized greeting'],
            'required_checks': [' '.join(command)]}], 'limits': {'working_seconds': 600}, 'uncapped_work': True})
        run.update(status='running', current_item_id='greeting', expected_feature_tip='tip', authorization_ref='grant')
        item = run['items'][0]
        item['status'] = 'working'
        task, engine = self.task, self.engine
        task.update(branch_run=run, limits=limits_from({'uncapped_work': True}), messages=[], worker_turns=0, compact_edits=True,
                    providers={'worker': {'model': 'worker'}, 'reviewer': {'model': 'reviewer'}})
        branch_disagreement.attach(task, item, branch_disagreement.repair({'defects': [{
            'criterion': 'Normalized greeting', 'location': 'app.py:3', 'expected': 'hello',
            'observed': 'Leading and trailing spaces', 'kind': 'executable',
            'support': 'The return literal contains spaces', 'reproduction': 'Assert Manager().run() == "hello"'
        }]}, 'disputed', []))
        runtime = Runtime(task)
        engine.remember_file_version(runtime, self.ws.read_file('app.py'))
        engine.fit_worker_context = Mock()
        engine.deliver_loop_guidance = Mock()
        engine.refresh_worker_conversation = Mock()
        engine.defer_route = Mock()
        engine.verification_argv.return_value = command
        def call(name, args, identity):
            return {'role': 'assistant', 'tool_calls': [{'id': identity, 'function': {
                'name': name, 'arguments': json.dumps(args)}}]}
        fixed = {'path': 'app.py', 'start_line': 3, 'end_line': 3, 'new_text': '        return "hello"\n'}
        responses = iter([
            call('replace_lines', fixed, 'blocked1'), call('replace_lines', fixed, 'blocked2'),
            call('write_file', {'path': 'test_app.py', 'content': 'replacement'}, 'exists1'),
            call('write_file', {'path': 'test_app.py', 'content': 'replacement'}, 'exists2'),
            call('append_text', {'path': 'test_app.py', 'text':
                '    def test_regression(self):\n        self.assertEqual(Manager().run(), "hello")\n'}, 'regression'),
            call('run_checks', {'command': ' '.join(command)}, 'failing'),
            call('replace_lines', fixed, 'repair'),
            call('run_checks', {'command': ' '.join(command)}, 'passing'),
            call('checkpoint', {'summary': 'Regression reproduced and fixed', 'uncertainties': ''}, 'done'),
        ])
        def request(rt, messages, tools, role):
            if role == 'reviewer':
                self.assertEqual([c['passed'] for c in task['checks']], [False, True])
                packet = json.loads(messages[1]['content'])
                self.assertEqual(packet['repair_review']['defects'][0]['reproduction'], 'Assert Manager().run() == "hello"')
                return call('review_decision', {'decision': 'APPROVE', 'candidate_id': 'fixed', 'defects': [],
                    'feedback': 'Both tests ran; greeting is normalized and original behavior preserved.',
                    'criteria_outcomes': {'Normalized greeting': {'passed': True, 'evidence': 'Source and regression'}}}, 'review')
            return next(responses)
        engine.request = Mock(side_effect=request)
        def identity(*args):
            return hashlib.sha256(((self.root / 'app.py').read_text() +
                                   (self.root / 'test_app.py').read_text()).encode()).hexdigest()
        def check(rt, requested):
            self.assertEqual(requested, ' '.join(command))
            namespace = {}
            exec((self.root / 'app.py').read_text(), namespace)
            exec((self.root / 'test_app.py').read_text(), namespace)
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(namespace['GreetingTests'])
            output = io.StringIO()
            result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
            self.assertEqual(result.testsRun, 2)
            record = {'passed': result.wasSuccessful(), 'exit_code': 0 if result.wasSuccessful() else 1,
                'outcome': 'passed' if result.wasSuccessful() else 'test_failure', 'command': command,
                'input_identity': identity(), 'run_id': str(len(task['checks'])), 'output': output.getvalue(),
                'digest': hashlib.sha256(task['patch'].encode()).hexdigest()}
            task['checks'].append(record)
            return record
        engine.checks = Mock(side_effect=check)
        # Reuse the existing in-memory review boundary; no Git workflow or model calls.
        with ExitStack() as stack:
            for target, value in [('cheapos.engine.automatic', True),
                    ('cheapos.coordinator_dispatch.consult', False),
                    ('cheapos.integration_preparation.observe', None),
                    ('cheapos.integration_preparation.automatic', None)]:
                stack.enter_context(patch(target, return_value=value))
            stack.enter_context(patch('cheapos.verification.evidence_identity', side_effect=identity))
            for name, value in [('candidate', {'id': 'fixed', 'checks': [], 'patch': 'greeting diff'}),
                    ('current_checks', task['checks']), ('review_packet', {'candidate_id': 'fixed', 'diff': 'greeting diff'}),
                    ('ready_receipt', 'receipt'), ('revalidate', None)]:
                stack.enter_context(patch.object(branch_review.evidence, name, return_value=value))
            engine._run_until_pause(runtime)
        self.assertEqual(task['status'], 'approved', task.get('error'))
        results = {m['tool_call_id']: json.loads(m['content']) for m in task['messages'] if m.get('role') == 'tool'}
        self.assertEqual(results['blocked2']['code'], 'repair_evidence_required')
        self.assertEqual(results['blocked2']['attempts'], 2)
        self.assertEqual(results['blocked2']['reproduction']['test_files'], ['test_app.py'])
        self.assertEqual(results['exists2']['code'], 'file_already_exists')
        self.assertEqual(results['exists2']['attempts'], 2)
        self.assertEqual(item['review_repair']['probe_observed']['run_id'], '0')
        self.assertTrue((self.root / 'test_app.py').read_text().startswith(test_text))
        self.assertEqual(engine.defer_route.call_count, 2)
        self.assertEqual(task['worker_turns'], 9)
        self.assertEqual(sum(c.args[-1] == 'reviewer' for c in engine.request.call_args_list), 1)
        self.assertEqual(item['ready_receipt'], 'receipt')
        self.assertEqual(task['checkpoints'][0]['decision'], 'APPROVE')

    def test_constraint_recovery_survives_reload_and_uses_current_test_evidence(self):
        from cheapos import branch_disagreement
        from cheapos.edit_recovery import constraint_feedback
        from test_branch_disagreement import defect
        tests = self.root / 'tests'
        tests.mkdir()
        (tests / 'test_precision.py').write_text('class Checks:\n    pass\n')
        item = {'id': 'one', 'acceptance_criteria': ['exact values'],
                'required_checks': ['python3 -m unittest tests.test_precision.Checks -v']}
        self.task['branch_run'] = {'current_item_id': 'one', 'items': [item]}
        branch_disagreement.attach(self.task, item, branch_disagreement.repair({'defects': [defect('executable')]}, 'candidate', []))
        error = FileEditConstraint('repair_evidence_required', 'Reproduce first')
        result = constraint_feedback(self.task, self.ws, {'path': 'app.py'}, error)
        self.assertEqual(result['reproduction']['test_files'], ['tests/test_precision.py'])
        self.assertIn('1: class Checks:', result['reproduction']['current_test_file']['content'])
        restored = json.loads(json.dumps(self.task))
        result = constraint_feedback(restored, self.ws, {'path': './other.py'}, error)
        self.assertEqual(result['attempts'], 2)
        self.assertFalse(result['executed'])
        self.assertEqual(restored['checks'], [])
        with patch.object(self.ws, 'read_file', side_effect=ValueError('File too large')):
            result = constraint_feedback(restored, self.ws, {'path': 'app.py'}, error)
        self.assertEqual(result['reproduction']['test_file_read_error'], 'File too large')
        self.assertEqual(result['reproduction']['planned_checks'], [['python3', '-m', 'unittest', 'tests.test_precision.Checks', '-v']])
        restored['providers']['worker'] = {'model': 'different-worker'}
        self.assertEqual(constraint_feedback(restored, self.ws, {'path': 'app.py'}, error)['attempts'], 1)

    def test_oversized_replacement_retains_file_and_returns_small_edit_context(self):
        self.engine.remember_file_version(self.runtime, self.ws.read_file('app.py'))
        args = {'path': 'app.py', 'start_line': 3, 'end_line': 3, 'new_text': 'x' * (MAX_EDIT_BYTES + 1)}
        with self.assertRaises(FileEditConstraint) as failure:
            self.ws.replace_lines(**args, expected_hash=self.ws.read_file('app.py')['hash'])
        self.assertEqual(failure.exception.code, 'edit_too_large')
        result = self.engine.recover_edit_constraint(self.runtime, args, failure.exception)
        self.assertFalse(result['changed'])
        self.assertEqual(result['edit_size']['fields']['new_text'], {'utf8_bytes': MAX_EDIT_BYTES + 1, 'lines': 1})
        self.assertEqual(result['edit_size']['exceeded'], ['new_text.utf8_bytes'])
        self.assertIn('3:         return', result['current_file']['content'])
        self.assertEqual((self.root / 'app.py').read_text(), self.original)
        self.assertFalse(self.task.get('compact_edits'))

    def test_edit_size_feedback_distinguishes_bytes_lines_and_removed_range(self):
        for content, removed, expected in [
                ('é' * 1501, 1, ['new_text.utf8_bytes']),
                ('x\n' * 81, 1, ['new_text.lines']),
                ('', 81, ['removed_lines']),
                ('x\n' * 80 + 'z' * 3114, 34, ['new_text.utf8_bytes', 'new_text.lines'])]:
            with self.subTest(expected=expected):
                error = edit_size_violation({'new_text': content}, max_bytes=3000, max_lines=80, removed_lines=removed)
                self.assertEqual(error.code, 'edit_too_large')
                self.assertEqual(error.details['edit_size']['exceeded'], expected)
                self.assertEqual(error.details['edit_size']['fields']['new_text']['utf8_bytes'], len(content.encode()))
                self.assertEqual(error.details['edit_size']['removed_lines'], removed)
                self.assertNotIn('é', str(error))
                self.assertEqual(set(error.details['edit_size']['fields']['new_text']), {'utf8_bytes', 'lines'})
        self.assertIsNone(edit_size_violation({'new_text': 'x\n' * 79 + 'z' * 2842}, removed_lines=80))
        with patch('cheapos.engine.automatic', return_value=True):
            for name, args, dimension, maximum in [
                    ('write_file', {'path': 'new.py', 'content': '#' * (MAX_CREATE_FILE_BYTES + 1)}, 'content', MAX_CREATE_FILE_BYTES),
                    ('append_text', {'path': 'app.py', 'text': '#' * (MAX_EDIT_BYTES + 1)}, 'text', MAX_EDIT_BYTES),
                    ('replace_text', {'path': 'app.py', 'old_text': '#' * (MAX_EDIT_BYTES + 1), 'new_text': ''}, 'old_text', MAX_EDIT_BYTES)]:
                with self.subTest(tool=name):
                    self.task.pop('compact_edits', None)
                    with self.assertRaises(FileEditConstraint) as failure:
                        self.engine.file_tool(self.task, name, args)
                    size = failure.exception.details['edit_size']
                    self.assertEqual(size['limits']['utf8_bytes'], maximum)
                    self.assertIn(dimension + '.utf8_bytes', size['exceeded'])
        self.assertFalse((self.root / 'new.py').exists())
        self.assertEqual((self.root / 'app.py').read_text(), self.original)

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
        # Reproduce the live path: prior syntax recovery allowed exact text
        # even after compact line-edit mode had already been selected.
        self.edit('    def run(self):', 'def run(self):')
        self.edit('    def run(self):', 'def run(self):')
        task = self.task
        task.update(limits=limits_from({'uncapped_work': True}), messages=[], worker_turns=0)
        runtime = Runtime(task)
        engine = self.engine
        engine.fit_worker_context = Mock()
        engine.deliver_loop_guidance = Mock()
        engine.refresh_worker_conversation = Mock()
        engine.defer_route = Mock()

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
            if task['worker_turns'] == 3:
                offered = {tool['function']['name'] for tool in tools}
                self.assertIn('replace_lines', offered)
                self.assertIn('replace_text', offered)
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
                patch('cheapos.coordinator_dispatch.consult', return_value=False), \
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
        self.assertEqual(errors[1]['code'], 'text_edit_rejected')
        self.assertEqual(errors[1]['attempts'], 2)
        engine.defer_route.assert_called_once()
        self.assertFalse(task.get('compact_edits'))
        self.assertEqual(task['worker_turns'], 4)
        self.assertEqual(task['review_count'], 1)
        self.assertEqual(task['checkpoints'][0]['decision'], 'APPROVE')
        engine.checks.assert_called_once()

    def test_text_mismatch_is_not_reexecuted_after_reload_and_new_version_can_retry(self):
        args = {'path': 'app.py', 'old_text': 'absent', 'new_text': 'replacement'}
        operation = Mock(side_effect=self.ws.replace_text)
        first = edit_history.apply(self.task, self.ws, 'replace_text', args, operation)
        restored = json.loads(json.dumps(self.task))
        second = edit_history.apply(restored, self.ws, 'replace_text', {**args, 'path': './app.py'}, operation)
        self.assertEqual(operation.call_count, 1)
        self.assertEqual(second['attempts'], 2)
        self.assertEqual(first['hash'], second['hash'])
        self.assertEqual(second['matches'], 0)
        self.assertFalse(second['executed'])
        self.assertFalse(second['changed'])
        self.assertEqual((self.root / 'app.py').read_text(), self.original)
        self.assertNotIn('edit_history', restored)
        (self.root / 'app.py').write_text(self.original + '# new file evidence\n')
        third = edit_history.apply(restored, self.ws, 'replace_text', args, operation)
        self.assertEqual(third['attempts'], 1)
        self.assertEqual(operation.call_count, 2)
        restored['branch_run'] = {'current_item_id': 'new-item'}
        fourth = edit_history.apply(restored, self.ws, 'replace_text', args, operation)
        self.assertEqual(fourth['attempts'], 1)
        self.assertEqual(operation.call_count, 3)

    def test_malformed_then_empty_creation_hands_off_and_finishes_without_operator_rescue(self):
        from cheapos.engine import Runtime, limits_from
        from cheapos.worker_conversation import continue_session
        task = self.task
        task.update(limits=limits_from({'uncapped_work': True}), messages=[], worker_turns=0,
                    providers={'worker': {'model': 'first'}})
        runtime = Runtime(task)
        engine = self.engine
        engine.fit_worker_context = Mock()
        engine.deliver_loop_guidance = Mock()
        def refresh(rt):
            continue_session(task, [{'role': 'system', 'content': 'Create greeting.py and verify it.'}], 'repair')
            rt.compact_context_ready = True
        engine.refresh_worker_conversation = refresh
        def handoff(*args):
            task['providers']['worker']['model'] = 'replacement'
        engine.defer_route = Mock(side_effect=handoff)
        target = self.root / 'greeting.py'
        engine.refresh_changes = lambda t: t.update(
            patch=target.read_text() if target.exists() else '',
            changes=[{'path': 'greeting.py'}] if target.exists() else [])
        def call(name, arguments, identity):
            return {'role': 'assistant', 'tool_calls': [{'id': identity, 'function': {
                'name': name, 'arguments': arguments}}]}
        replies = iter([call('write_file', '{broken', str(n)) for n in range(3)] +
                       [call('write_file', '{}', str(n)) for n in range(3, 6)] + [
                           call('write_file', json.dumps({'path': 'greeting.py', 'content': 'greeting = "hello"\n'}), 'fixed'),
                           call('checkpoint', '{"summary":"Greeting implemented","uncertainties":""}', 'done')])
        def request(rt, messages, tools, role):
            if role == 'reviewer':
                self.assertTrue(task['checks'][-1]['passed'])
                self.assertEqual(task['checkpoints'][-1]['diff'], target.read_text())
                return call('review_decision', '{"decision":"APPROVE","feedback":"Greeting verified."}', 'review')
            if task['worker_turns'] <= 6:
                self.assertFalse(target.exists())
            else:
                self.assertEqual(task['providers']['worker']['model'], 'replacement')
                engine.defer_route.assert_called_once()
            return next(replies)
        engine.request = Mock(side_effect=request)
        def check(*args):
            namespace = {}
            exec(target.read_text(), namespace)
            self.assertEqual(namespace['greeting'], 'hello')
            result = {'passed': True, 'command': task['check_command'],
                      'digest': hashlib.sha256(task['patch'].encode()).hexdigest()}
            task['checks'].append(result)
            return result
        engine.checks = Mock(side_effect=check)
        with patch('cheapos.engine.automatic', return_value=True), \
                patch('cheapos.engine.reconciliation.ensure_resolved'), \
                patch('cheapos.integration_preparation.observe'), \
                patch('cheapos.integration_preparation.automatic'):
            engine._run_until_pause(runtime)
        self.assertEqual(task['status'], 'approved', task.get('error'))
        errors = [e['detail'] for e in task['events'] if e['kind'] == 'tool_error']
        self.assertEqual(len(errors), 6)
        self.assertTrue(all(e['code'] == 'invalid_tool_arguments' and not e['executed'] for e in errors))
        self.assertEqual(task['worker_turns'], 8)
        self.assertEqual(task['review_count'], 1)
        engine.checks.assert_called_once()

    def test_ambiguous_text_rejection_keeps_content_and_supplies_current_evidence(self):
        (self.root / 'app.py').write_text('value = "hello hello"\n')
        result = self.edit('hello', 'hi')
        self.assertEqual(result['code'], 'text_edit_rejected')
        self.assertEqual(result['matches'], 2)
        self.assertFalse(result['executed'])
        self.assertEqual((self.root / 'app.py').read_text(), 'value = "hello hello"\n')
        self.assertIn('1: value =', result['current_file']['content'])
        self.assertEqual(self.task['events'][-1]['kind'], 'tool_error')
        self.assertNotIn('edit_history', self.task)

    def test_text_failure_after_syntax_rejections_recovers_with_lines(self):
        self.edit('    def run(self):', 'def run(self):')
        self.edit('    def run(self):', 'def run(self):')
        self.edit('missing', 'fixed')
        rejected = self.edit('missing', 'fixed')
        self.assertEqual(rejected['code'], 'text_edit_rejected')
        self.assertEqual(rejected['attempts'], 2)
        self.task['compact_edits'] = True
        current = self.ws.read_file('app.py')
        self.engine.file_tool(self.task, 'replace_lines', {
            'path': 'app.py', 'start_line': 3, 'end_line': 3,
            'new_text': '        return "hello"\n', 'expected_hash': current['hash']})
        self.assertIn('return "hello"', (self.root / 'app.py').read_text())
        self.assertEqual(self.task['text_edit_recovery']['files'], {})

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
        with patch('cheapos.structural_telemetry.validation', side_effect=RuntimeError('collector unavailable')):
            result = self.edit('hello', 'hello2')
            self.assertTrue(result['changed'])
            self.edit('hello2', 'hello')
        self.task.pop('edit_history', None)
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
