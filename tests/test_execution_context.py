"""Small mode/prompt/tool policy cases, without model or Git fixtures."""
import unittest
from cheapos import execution_context as context
from cheapos.engine import Engine, UNATTENDED_TOOLS, CHAT_TOOLS, worker_system
from cheapos.providers import ProviderError


class ExecutionContextTests(unittest.TestCase):
    def test_modes_do_not_depend_only_on_conversational_flag(self):
        cases=[({},'worker'),({'conversational':True},'interactive'),
               ({'conversational':True,'branch_run':{'phase':'planning'}},'planning'),
               ({'conversational':True,'branch_run':{'authorization_ref':{'id':'a'}}},'unattended'),
               ({'conversational':True,'status':'reviewing'},'review')]
        for task,expected in cases:
            self.assertEqual(context.mode(task),expected)
        self.assertEqual(context.mode({},purpose='branch_planning'),'planning')

    def test_unattended_prompts_and_tools_retain_blocker_and_receipt_boundary(self):
        task={'conversational':True,'branch_run':{'authorization_ref':'a'}}
        prompt=worker_system(task)
        self.assertIn('report_blocker',prompt);self.assertIn('controller owns branch commits',prompt)
        self.assertNotIn('user clicks Approve & commit',prompt)
        names={t['function']['name'] for t in UNATTENDED_TOOLS}
        self.assertIn('report_blocker',names);self.assertNotIn('ask_user',names)
        self.assertIn('ask_user',{t['function']['name'] for t in CHAT_TOOLS})
        self.assertNotIn('ask_user',context.guidance(task,'If blocked, ask_user.'))

    def test_unoffered_tool_rejects_entire_mixed_response_and_blocker_requires_evidence(self):
        message={'tool_calls':[{'function':{'name':'write_file'}},{'function':{'name':'ask_user'}}]}
        with self.assertRaises(ProviderError) as caught:
            Engine.validate_offered_tools(message,UNATTENDED_TOOLS)
        self.assertEqual(caught.exception.code,'unsupported_tool')
        with self.assertRaises(ValueError):context.blocker({'question':'Which? '})
        args={'question':'Which account?','inspected_evidence':'README omits account selection.',
              'why_blocked':'Sending to an account needs operator selection.'}
        self.assertEqual(context.blocker(args),args)
