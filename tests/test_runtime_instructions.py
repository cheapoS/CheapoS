"""Prompt wiring and provider-boundary checks without Git, sockets or inference."""
import ast
import copy
import json
import unittest
from pathlib import Path

from cheapos import branch_planner, coordinator_recovery, discussion, engine, routing, startup, tools
from cheapos.instructions.runtime import (
    PROFILES, TOOL_CONTRACT, audit_tools, profile_rules, prompt, text, validation, with_tools,
)


class RuntimeInstructionTests(unittest.TestCase):
    def test_entry_points_use_registered_current_profiles(self):
        for profile, delivered in (
            ('worker', tools.WORKER_SYSTEM), ('interactive', tools.CHAT_SYSTEM),
            ('planner', branch_planner.SYSTEM), ('reviewer', engine.REVIEW_SYSTEM),
            ('discussion', discussion.SYSTEM), ('coordinator_chat', routing.COORDINATOR_SYSTEM),
            ('coordinator_recovery', coordinator_recovery.SYSTEM),
            ('greeting', discussion.greeting_messages({'prompt': 'hi'})[0]['content']),
            ('startup_greeting', startup.GREETING[0]['content']),
        ):
            with self.subTest(profile=profile):
                self.assertEqual(delivered, prompt(profile))
        for name in PROFILES:
            self.assertTrue(profile_rules(name), name)
        self.assertNotIn('NEVER output code', prompt('interactive'))
        self.assertIn('examples may include code', prompt('interactive'))
        self.assertNotIn('(< 2s)', text('validation.change_scoped'))
        self.assertNotIn('(< 2s)', prompt('planner'))
        self.assertNotIn('This pauses for explicit user approval', prompt('reviewer'))

    def test_real_role_tools_match_phase_contracts_and_detect_missing_readers(self):
        for profile, offered in (
            ('worker', tools.WORKER_TOOLS), ('unattended', tools.UNATTENDED_TOOLS),
            ('interactive', tools.CHAT_TOOLS), ('reviewer', tools.REVIEW_TOOLS),
            ('planner', branch_planner.TOOLS), ('coordinator_chat', [routing.DELEGATE_TOOL]),
            ('coordinator_recovery', []), ('greeting', []), ('startup_greeting', []),
        ):
            self.assertEqual(audit_tools(profile, offered), [], profile)
        self.assertTrue(audit_tools('planner', [branch_planner.TOOLS[0]]))
        self.assertTrue(audit_tools('greeting', tools.WORKER_TOOLS))
        self.assertTrue(audit_tools('discussion', tools.CHAT_TOOLS))
        self.assertTrue(audit_tools('review_decision_coaching', tools.REVIEW_TOOLS))

    def test_contract_refreshes_without_growing_history_or_mutating_evidence(self):
        messages = [{'role': 'system', 'content': prompt('reviewer')},
                    {'role': 'user', 'content': 'Candidate and checks'},
                    {'role': 'assistant', 'tool_calls': [{'id': 'r', 'function': {'name': 'read_file'}}]},
                    {'role': 'tool', 'tool_call_id': 'r', 'content': 'Saved source'}]
        before = copy.deepcopy(messages)
        first = with_tools(messages, tools.REVIEW_TOOLS)
        decision = next(t for t in tools.REVIEW_TOOLS if t['function']['name'] == 'review_decision')
        second = with_tools(first, [decision], {'type': 'function', 'function': {'name': 'review_decision'}})
        contract = json.loads(second[0]['content'].rsplit('\n', 1)[1])
        self.assertEqual(contract['available_tools'], ['review_decision'])
        self.assertEqual(contract['required_call'], 'review_decision')
        self.assertEqual(contract['decision_values']['review_decision'],
                         decision['function']['parameters']['properties']['decision']['enum'])
        self.assertEqual(second[0]['content'].count(TOOL_CONTRACT), 1)
        self.assertEqual(second[1:], before[1:])
        self.assertEqual(messages, before)
        self.assertEqual(len(second), len(messages))
        self.assertEqual(with_tools(second, [], 'auto')[0]['content'].count(TOOL_CONTRACT), 1)

    def test_final_provider_receives_fresh_worker_policy_and_actual_tools_once(self):
        from tests.test_transport import TransportTests
        for unattended, read_only in ((False, False), (False, True), (True, False)):
            with self.subTest(unattended=unattended, read_only=read_only):
                app, runtime, _ = TransportTests().harness()
                task = runtime.task
                task['conversational'] = True
                if unattended:
                    task['branch_run'] = {'authorization_ref': {'id': 'approved'}}
                if read_only:
                    from cheapos import work_policy
                    task['prompt'] = work_policy.READ_ONLY_STARTERS[0]
                offered = tools.UNATTENDED_TOOLS if unattended else tools.CHAT_TOOLS
                if read_only:
                    offered = work_policy.offered_tools(task, offered)
                saved = [{'role': 'system', 'content': 'Stale policy'},
                         {'role': 'user', 'content': 'Latest operator direction'}]
                before = copy.deepcopy(saved)
                received = []
                class Provider:
                    def complete(self, messages, available, maximum):
                        received.append((messages, available))
                        return {'content': 'Done'}, {'prompt_tokens': 2, 'completion_tokens': 3, 'cost': 0}
                app.provider_factory = lambda *args: Provider()
                app._request_attempt(runtime, saved, offered, 'worker')
                delivered, actual = received[0]
                policy = delivered[0]['content']
                self.assertNotIn('Stale policy', policy)
                self.assertEqual(policy.count(TOOL_CONTRACT), 1)
                self.assertIn(engine.worker_system(task), policy)
                if unattended:
                    self.assertEqual(policy.count(text('workflow.unattended_policy')), 1)
                    self.assertNotIn('Approve & commit', policy)
                if read_only:
                    self.assertIn('read-only explanation', policy)
                    self.assertNotIn('checkpoint', {t['function']['name'] for t in actual})
                contract = json.loads(policy.rsplit('\n', 1)[1])
                self.assertEqual(contract['available_tools'], [t['function']['name'] for t in actual])
                self.assertEqual(saved, before)
                self.assertEqual(delivered[-1], before[-1])

    def test_validation_text_follows_authority_not_elapsed_seconds(self):
        self.assertEqual(validation({}), text('validation.change_scoped'))
        self.assertEqual(validation({'full_suite_approved': True}), text('validation.full_suite_mandatory'))
        # A flag is not persisted branch command authorization.
        self.assertEqual(validation({'branch_run': {}, 'full_suite_approved': True}), text('validation.change_scoped'))

    def test_other_roles_receive_current_contract_at_provider_boundary(self):
        from tests.test_transport import TransportTests
        decision = next(t for t in tools.REVIEW_TOOLS if t['function']['name'] == 'review_decision')
        for role, purpose, profile, offered in (
            ('planner', 'branch_planning', 'planner', branch_planner.TOOLS),
            ('reviewer', None, 'review_decision_coaching', [decision]),
            ('coordinator', 'coordinator_recovery', 'coordinator_recovery', []),
            ('coordinator', None, 'coordinator_chat', [routing.DELEGATE_TOOL]),
            ('worker', 'chat_reply', 'greeting', []),
        ):
            with self.subTest(profile=profile):
                app, runtime, _ = TransportTests().harness()
                task = runtime.task
                task['providers'][role] = dict(task['providers']['worker'])
                task['usage'][role] = {'tokens': 0, 'cost': 0}
                original = [{'role': 'system', 'content': prompt(profile)},
                            {'role': 'user', 'content': 'Saved evidence and request'}]
                received = []
                class Provider:
                    def complete(self, messages, available, maximum):
                        received.append((messages, available))
                        return {'content': 'Done'}, {'prompt_tokens': 2, 'completion_tokens': 3, 'cost': 0}
                app.provider_factory = lambda *args: Provider()
                app._request_attempt(runtime, original, offered, role, purpose=purpose)
                messages, actual = received[0]
                self.assertTrue(messages[0]['content'].startswith(prompt(profile)))
                contract = json.loads(messages[0]['content'].rsplit('\n', 1)[1])
                self.assertEqual(contract['available_tools'], [t['function']['name'] for t in actual])
                self.assertEqual(audit_tools(profile, actual), [])
                self.assertEqual(messages[1:], original[1:])
                self.assertNotIn(TOOL_CONTRACT, original[0]['content'])

    def test_primary_prompts_cannot_be_reintroduced_as_inline_copies(self):
        root = Path(__file__).resolve().parents[1] / 'cheapos'
        for path in root.glob('*.py'):
            source = path.read_text()
            # Avoid parsing unrelated modules, while covering new entry points.
            if 'system' not in source and 'SYSTEM' not in source:
                continue
            file = path.name
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                    if any(n == 'SYSTEM' or n.endswith(('_SYSTEM', '_INSTRUCTION', '_GUIDANCE')) for n in names):
                        self.assertFalse(isinstance(node.value, ast.Constant) and isinstance(node.value.value, str),
                                         f'{file}:{node.lineno}: register policy in the catalog')
                if isinstance(node, ast.Dict):
                    fields = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
                    role, content = fields.get('role'), fields.get('content')
                    if isinstance(role, ast.Constant) and role.value == 'system':
                        self.assertFalse(isinstance(content, ast.Constant) and isinstance(content.value, str),
                                         f'{file}:{node.lineno}: register system prompt in the catalog')
