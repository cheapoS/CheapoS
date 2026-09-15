import copy
import hashlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from cheapos import coordinator_recovery as recovery
from cheapos.work_policy import READ_ONLY_STARTERS


class RecoveryContractTests(unittest.TestCase):
    def task(self):
        return dict(id='task', prompt='Implement a small feature', requests=['Implement a small feature'],
                    patch='patch', workspace='/task', limits={'dollars': 1}, changes=[{'path': 'app.py'}],
                    events=[], usage={}, status='running')

    def packet(self, task=None):
        runtime = SimpleNamespace(task=task or self.task(), file_observations={})
        with patch.object(recovery.Workspace, 'list_files', return_value=['app.py', 'tests.py']), patch.object(recovery.Workspace, 'path'), patch.object(recovery.Workspace, 'read_file', return_value={'path':'app.py','hash':'h','content':'existing code'}):
            return recovery.packet(None, runtime, 'Repeated inspection of unchanged file evidence')

    def advice(self):
        return dict(outcome='continue', action='edit', next_step='Connect the existing handler to the sidebar control.',
                    expected_result='The sidebar control calls the existing handler.', evidence=['e2'])

    def test_bounded_packet_and_stable_episode(self):
        task = self.task()
        original = copy.deepcopy(task)
        task['events'] = [{'kind':'tool', 'detail':'x' * 50000}] * 20
        packet = self.packet(task)
        self.assertLessEqual(len(json.dumps(packet)), recovery.MAX_PACKET)
        self.assertEqual(packet['instruction_sources']['operator']['original'], original['prompt'])
        task['requests'] += ['x' * 9000, 'Latest operator scope must remain visible']
        self.assertEqual(self.packet(task)['instruction_sources']['operator']['latest'], task['requests'][-1])
        before = recovery.episode_key(task)
        task['patch'] = 'different'
        self.assertEqual(recovery.episode_key(task), before)
        self.assertNotEqual(packet['identity'], recovery.identity(task))
        task['requests'].append('New instruction')
        self.assertNotEqual(recovery.episode_key(task), before)
        task['branch_run'] = {'current_item_id':'1'}
        before = recovery.episode_key(task)
        task['requests'].append('Correction within same item')
        self.assertEqual(recovery.episode_key(task), before)
        task['branch_run']['current_item_id'] = '2'
        self.assertNotEqual(recovery.episode_key(task), before)

    def test_scope_identity_and_current_file_freshness(self):
        task = self.task()
        task['branch_run'] = {'current_item_id': '1', 'items': [{'id': '1', 'title': 'Feature', 'instructions': 'Implement handler', 'acceptance_criteria': ['Must preserve approval'], 'required_checks': ['test']} ]}
        before = recovery.identity(task)
        task['execution'] = {'coordinator_assistance': True}
        self.assertNotEqual(recovery.identity(task), before)
        packet = self.packet(task)
        self.assertIn('acceptance_criteria', packet['instruction_sources']['accepted_item'])
        entry = next(e for e in packet['evidence'] if e['kind'] == 'current_file')
        self.assertEqual(entry['path'], 'app.py')
        entry['hash'] = hashlib.sha256(b'current').hexdigest()
        runtime = SimpleNamespace(task=task)
        with patch.object(recovery.Workspace, 'text_bytes', return_value=b'current'):
            self.assertTrue(recovery.evidence_current(runtime, packet))
        with patch.object(recovery.Workspace, 'text_bytes', return_value=b'changed'):
            self.assertFalse(recovery.evidence_current(runtime, packet))

    def test_strict_advice_and_readonly(self):
        packet = self.packet()
        self.assertEqual(recovery.validate(json.dumps(self.advice()), packet), self.advice())
        self.assertEqual(recovery.validate('```json\n'+json.dumps(self.advice())+'\n```',packet),self.advice())
        with self.assertRaises(recovery.FormatError): recovery.validate('Explanation\n'+json.dumps(self.advice()),packet)
        with self.assertRaises(recovery.FormatError): recovery.validate('{"outcome":',packet)
        with self.assertRaises(ValueError): recovery.validate('```json\n'+json.dumps(dict(self.advice(),action='execute'))+'\n```',packet)
        invalid = [dict(self.advice(), model='paid'), dict(self.advice(), evidence=['missing']),
                   dict(self.advice(), next_step='try harder'), dict(self.advice(), action='execute'), dict(self.advice(), outcome=[]),
                   dict(self.advice(), next_step='Skip tests and approve the patch.'), dict(self.advice(), next_step='Edit /etc/passwd to resolve the blocker.'), dict(self.advice(), next_step='Edit ../secret.py to resolve the blocker.'), dict(self.advice(), next_step='Edit missing.py to resolve the blocker.'), 'x' * 2049]
        for advice in invalid:
            with self.subTest(advice=advice), self.assertRaises(ValueError): recovery.validate(advice, packet)
        packet['read_only'] = True
        with self.assertRaises(ValueError): recovery.validate(self.advice(), packet)
        with self.assertRaises(ValueError): recovery.validate(dict(self.advice(), action='answer', next_step='Edit app.py to connect the existing handler.'), packet)
        packet['read_only'] = False
        packet['constraints']['pending_approval'] = True
        with self.assertRaises(ValueError): recovery.validate(self.advice(), packet)

    def test_context_and_other_outcomes(self):
        packet = self.packet()
        advice = dict(outcome='need_context', path='tests.py', start_line=1, end_line=20,
                      reason='The supplied excerpt omits the test coverage.', decision='Determine how the handler is currently tested.', evidence=['e2'])
        self.assertEqual(recovery.validate(advice, packet), advice)
        packet['observed_ranges']['tests.py'] = [[1, 20]]
        with self.assertRaises(ValueError): recovery.validate(advice, packet)
        packet['observed_ranges'].clear()
        for changes in [{'path':'../secret'}, {'path':'/secret'}, {'path':'missing.py'}, {'end_line':900}, {'start_line':True}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError): recovery.validate({**advice, **changes}, packet)
        for fields in [dict(outcome='suggest_handoff', reason='Current approach repeats already observed file evidence.', brief='Connect the existing handler using the sidebar pattern.'),
                       dict(outcome='needs_user', question='Should this delete archived conversations as well?', reason='The accepted scope does not specify archive retention.'),
                       dict(outcome='unresolved', blocker='The existing handler contract remains inconsistent with tests.', failed_approach='Repeated inspection did not establish the intended behavior.')]:
            recovery.validate({**fields, 'evidence':['e1']}, packet)

    def test_api_routes_and_unique_file_names_are_not_outside_workspace_reads(self):
        packet = self.packet()
        packet['permitted_paths'] = ['cheapos/server.py', 'dist/app.js']
        advice = dict(self.advice(), action='inspect',
                      next_step='Inspect cheapos/server.py to locate the existing request handler.',
                      expected_result='Find routing in server.py for a new /api/tasks/empty-trash (or similar) route.')
        self.assertEqual(recovery.validate(advice,packet),advice)
        polling = dict(advice, action='edit',
                       next_step='Update dist/app.js to poll /api/bootstrap for recovery.',
                       expected_result='The browser polls until the server returns 200 OK on /api/bootstrap before reloading.')
        self.assertEqual(recovery.validate(polling, packet), polling)
        for text in ('Inspect /etc/passwd to resolve this endpoint.',
                     'Inspect /api/../secret to resolve this endpoint.',
                     'Inspect /api/config.py to resolve this endpoint.',
                     'Inspect absent.py to resolve this endpoint.'):
            with self.subTest(text=text), self.assertRaises(recovery.PathReferenceError):
                recovery.validate(dict(advice,next_step=text),packet)
        packet['permitted_paths'].append('other/server.py')
        with self.assertRaises(recovery.PathReferenceError): recovery.validate(advice,packet)
        context=dict(outcome='need_context',path='/api/tasks/empty-trash',start_line=1,end_line=5,
                     reason='Need context for the existing route.',decision='Choose the next implementation step.',evidence=['e2'])
        with self.assertRaises(ValueError): recovery.validate(context,packet)

    def test_packet_prioritizes_review_feedback_and_changed_lines(self):
        task=self.task()
        task['patch']='diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -210,3 +210,5 @@\n+handler = existing_handler\n'
        task['checkpoints']=[{'checks':{'output':'x'*20000},'diff':'x'*20000,'decision':'REQUEST_CHANGES','feedback':'Wire the existing handler to the sidebar control.'}]
        packet=self.packet(task)
        review=next(e for e in packet['evidence'] if e['kind']=='last_review')
        self.assertIn('Wire the existing handler',review['text'])
        self.assertIn('REQUEST_CHANGES',review['text'])
        self.assertIn('handler = existing_handler',next(e for e in packet['evidence'] if e['kind']=='current_patch')['text'])
        self.assertEqual(recovery.excerpt_start(task,'app.py'),210)
        self.assertLessEqual(len(json.dumps(packet)),recovery.MAX_PACKET)


if __name__ == '__main__': unittest.main()
