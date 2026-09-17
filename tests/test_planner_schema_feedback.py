"""Pure proposal parsing; no network, repository copies, or waiting."""
import copy
import json
import unittest
from cheapos import branch_planner, branch_runs


class PlannerSchemaFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.limits = {'dollars': 0, 'working_seconds': 900, 'requests': 30}
        check = 'python3 -B -m unittest tests.test_reader'
        self.plan = {'items': [{'id': 'one', 'title': 'Reader', 'instructions': 'Read Unicode',
            'dependencies': [], 'acceptance_criteria': ['Preserve Unicode'], 'required_checks': [check]}],
            'limits': self.limits.copy(), 'final_checks': [check]}

    def parse(self, plan, **extra):
        reply = {'tool_calls': [{'id': 'p', 'function': {'name': 'propose_branch_plan', 'arguments':
            json.dumps({'status': 'plan', 'plan': plan, 'clarification': '', **extra})}}]}
        choices = []
        result = branch_planner._parse(reply, self.limits, assumptions=choices)
        return result, choices

    def test_nested_assumptions_preserved_in_instructions_without_extra_round_trip(self):
        self.plan['assumptions'] = ['Use standard library', 'Preserve Unicode']
        result, choices = self.parse(self.plan, assumptions=['Preserve Unicode'])
        self.assertEqual(choices, ['Preserve Unicode', 'Use standard library'])
        self.assertIn('Use standard library', result['items'][0]['instructions'])
        self.assertNotIn('assumptions', result)
        self.assertEqual(result['limits'], self.limits)

    def test_invalid_assumptions_are_not_silently_discarded(self):
        for choices in ('not a list', [''], [1], ['a'] * 13):
            self.plan['assumptions'] = choices
            with self.assertRaisesRegex(ValueError, 'plan.assumptions'):
                self.parse(self.plan)
        self.plan['assumptions'] = [str(i) for i in range(12)]
        with self.assertRaisesRegex(ValueError, 'at most twelve'):
            self.parse(self.plan, assumptions=['another'])

    def test_unknown_field_feedback_names_the_exact_location(self):
        self.plan['summary'] = 'unrecognized'
        with self.assertRaisesRegex(ValueError, r'plan.summary'):
            self.parse(self.plan)
        del self.plan['summary']
        self.plan['items'][0]['files'] = ['reader.py']
        with self.assertRaisesRegex(ValueError, r'plan.items\[0\].files'):
            self.parse(self.plan)
        self.plan['items'][0] = 'broken'
        with self.assertRaisesRegex(ValueError, r'plan.items\[0\] must be an object'):
            branch_runs.validate_plan(self.plan)

    def test_authorized_limits_stay_authoritative(self):
        for field, value in [('dollars', 1), ('requests', 40)]:
            changed = copy.deepcopy(self.plan)
            changed['limits'][field] = value
            with self.assertRaisesRegex(ValueError, 'differing fields: ' + field):
                self.parse(changed)
