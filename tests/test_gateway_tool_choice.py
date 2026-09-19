"""Exercise gateway dispatch through serialized HTTP; no sockets, waits, or Git."""
import json
import shlex
import sys
import threading
import tempfile
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import branch_planner
from cheapos.gateways import gateway_for


class GatewayToolChoiceTests(unittest.TestCase):
    def setUp(self):
        self.response = Mock()
        self.response.__enter__ = Mock(return_value=self.response)
        self.response.__exit__ = Mock(return_value=False)
        self.response.headers.get_content_type.return_value = 'application/json'
        self.reply({'content': 'Complete'})
        self.opener = Mock()
        self.opener.open.return_value = self.response
        for name, value in (('build_opener', self.opener), ('pacer.throttle', nullcontext())):
            replacement = patch('cheapos.providers.' + name, return_value=value)
            replacement.start()
            self.addCleanup(replacement.stop)

    def reply(self, message):
        self.response.read.return_value = json.dumps({
            'choices': [{'message': message}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1},
        }).encode()

    def gateway(self, kind='omniroute'):
        return gateway_for({'gateway': kind, 'model': 'fixture/planner',
                            'base_url': 'http://127.0.0.1:20128/v1',
                            'input_rate': 0, 'output_rate': 0})

    def test_explicit_choice_reaches_http_for_each_gateway_and_dispatch_method(self):
        for kind in ('omniroute', 'openai'):
            for method in ('chat', 'complete', 'complete_with_progress'):
                for choice in ('required', 'none', {
                        'type': 'function', 'function': {'name': 'propose_branch_plan'}}):
                    with self.subTest(gateway=kind, method=method, choice=choice):
                        args = [[], branch_planner.TOOLS, 512]
                        if method == 'complete_with_progress':
                            args.extend([Mock(), lambda: False])
                        message, usage = getattr(self.gateway(kind), method)(*args, tool_choice=choice)
                        body = json.loads(self.opener.open.call_args.args[0].data)
                        self.assertEqual(body['tool_choice'], choice)
                        self.assertEqual(body['tools'], branch_planner.TOOLS)
                        self.assertEqual(body['stream'], method == 'complete_with_progress')
                        self.assertFalse(body['parallel_tool_calls'])
                        self.assertEqual(message['content'], 'Complete')
                        self.assertEqual(usage['completion_tokens'], 1)

    def test_three_argument_calls_keep_automatic_choice(self):
        for kind in ('omniroute', 'openai'):
            for method in ('chat', 'complete'):
                with self.subTest(gateway=kind, method=method):
                    getattr(self.gateway(kind), method)([], branch_planner.TOOLS, 512)
                    body = json.loads(self.opener.open.call_args.args[0].data)
                    self.assertEqual(body['tool_choice'], 'auto')

    def test_discovery_closes_with_forced_proposal_and_retained_evidence_on_wire(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        inputs = {'source': temp.name, 'prompt': 'Suggest one improvement before changing anything'}
        inputs['hash'] = branch_planner._digest(inputs)
        runtime = SimpleNamespace(task={'planning_limits': {'dollars': 0}},
                                  stop=threading.Event(), guard=Mock())
        expected = {'items': [{'id': 'docs', 'title': 'Improve docs', 'instructions': 'Clarify setup',
                              'dependencies': [], 'acceptance_criteria': ['Setup is clear'],
                              'required_checks': [shlex.join([sys.executable, '-m', 'unittest', 'tests.test_docs'])]}],
                    'limits': {'dollars': 0}, 'final_checks': [shlex.join([sys.executable, '-m', 'unittest', 'tests.test_docs'])]}
        bodies = []

        def respond(request, **kwargs):
            body = json.loads(request.data)
            bodies.append(body)
            choice = body['tool_choice']
            name = choice['function']['name'] if isinstance(choice, dict) else 'inspect_project_file'
            arguments = ({'status': 'plan', 'plan': expected, 'clarification': ''}
                         if name == 'propose_branch_plan' else {'path': 'README.md'})
            self.reply({'tool_calls': [{'id': 'call-%s' % len(bodies), 'type': 'function',
                        'function': {'name': name, 'arguments': json.dumps(arguments)}}]})
            return self.response

        self.opener.open.side_effect = respond
        gateway = self.gateway()
        def request(runtime, messages, tools, role, purpose, **options):
            return gateway.complete(messages, tools, 512, **options)[0]

        with patch.object(branch_planner, 'project_context', return_value={}), \
                patch.object(branch_planner, 'inspect_project_file', return_value={
                    'path': 'README.md', 'contents': 'Existing setup instructions'}) as inspect:
            result = branch_planner.plan(SimpleNamespace(request=request), runtime, inputs)

        self.assertEqual(result, expected)
        self.assertEqual(inspect.call_count, 2)  # The second read repeats the same evidence.
        self.assertEqual(len(bodies), 3)
        self.assertTrue(all(body['tool_choice'] == 'auto' for body in bodies[:-1]))
        self.assertEqual(bodies[-1]['tool_choice'], {
            'type': 'function', 'function': {'name': 'propose_branch_plan'}})
        evidence = [m for m in bodies[-1]['messages'] if m['role'] == 'tool']
        self.assertEqual(len(evidence), 2)
        self.assertTrue(all('Existing setup instructions' in m['content'] for m in evidence))
        self.assertEqual(runtime.task['planning_limits'], {'dollars': 0})
