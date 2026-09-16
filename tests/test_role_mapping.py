"""RoleMapping contract: settings-level planner/worker/reviewer model binding."""

import copy
import unittest

from cheapos.agents import ROLES, RoleMapping


class RoleMappingTests(unittest.TestCase):
    def setUp(self):
        self.mapping = RoleMapping({
            'planner': {'planner-a', 'planner-b'},
            'worker': {'worker-a', 'planner-a'},
            'reviewer': {'reviewer-a'},
        })

    def test_roles_are_the_three_configured_agents(self):
        self.assertEqual(ROLES, ('planner', 'worker', 'reviewer'))

    def test_unset_fields_start_none(self):
        self.assertIsNone(self.mapping.planner)
        self.assertIsNone(self.mapping.worker)
        self.assertIsNone(self.mapping.reviewer)

    def test_candidates_are_validated_per_role(self):
        self.assertEqual(self.mapping.candidates('planner'), {'planner-a', 'planner-b'})
        self.assertEqual(set(self.mapping.candidates('worker')), {'worker-a', 'planner-a'})

    def test_unknown_role_rejected(self):
        for role in ('coordinator', 'planner ', 'Worker', ''):
            with self.assertRaises(ValueError):
                self.mapping.assign(role, 'planner-a')

    def test_unknown_candidate_rejected(self):
        with self.assertRaises(ValueError):
            self.mapping.assign('planner', 'not-configured')

    def test_empty_or_non_string_model_rejected(self):
        with self.assertRaises(ValueError):
            self.mapping.assign('planner', '')
        with self.assertRaises(ValueError):
            self.mapping.assign('planner', None)

    def test_assign_and_read_back(self):
        self.mapping.assign('planner', 'planner-a')
        self.assertEqual(self.mapping.get('planner'), 'planner-a')
        self.assertIsNone(self.mapping.worker)

    def test_reassign_same_role_replaces(self):
        self.mapping.assign('planner', 'planner-a')
        self.mapping.assign('planner', 'planner-b')
        self.assertEqual(self.mapping.get('planner'), 'planner-b')

    def test_duplicate_across_roles_rejected(self):
        self.mapping.assign('planner', 'planner-a')
        with self.assertRaises(ValueError):
            self.mapping.assign('worker', 'planner-a')

    def test_distinct_assignment_allows_overlapping_candidate_sets(self):
        self.mapping.assign('worker', 'worker-a')
        self.mapping.assign('reviewer', 'reviewer-a')
        self.mapping.assign('planner', 'planner-b')
        self.assertEqual(self.mapping.get('planner'), 'planner-b')

    def test_digest_is_stable_and_changes_with_selections(self):
        first = self.mapping.digest()
        self.assertEqual(first, self.mapping.digest())
        self.mapping.assign('planner', 'planner-a')
        self.assertNotEqual(self.mapping.digest(), first)
        self.mapping.assign('worker', 'worker-a')
        second = self.mapping.digest()
        self.assertEqual(second, self.mapping.digest())
        self.assertNotEqual(second, first)

    def test_digest_ignores_role_order_of_assignment(self):
        first = RoleMapping({'planner': {'p'}, 'worker': {'w'}, 'reviewer': {'r'}})
        second = RoleMapping({'planner': {'p'}, 'worker': {'w'}, 'reviewer': {'r'}})
        first.assign('planner', 'p')
        first.assign('worker', 'w')
        second.assign('worker', 'w')
        second.assign('planner', 'p')
        self.assertEqual(first.digest(), second.digest())

    def test_canonical_preserves_mapped_assignments_only(self):
        self.mapping.assign('planner', 'planner-a')
        self.mapping.assign('worker', 'worker-a')
        self.assertEqual(self.mapping.canonical(), {'planner': 'planner-a', 'worker': 'worker-a'})
        self.assertGreaterEqual(set(self.mapping.canonical()), {'planner', 'worker'})

    def test_canonical_with_no_selections_is_empty(self):
        self.assertEqual(self.mapping.canonical(), {})

    def test_canonical_preserves_independence_when_roles_unset(self):
        self.mapping.assign('planner', 'planner-a')
        self.mapping.assign('worker', 'worker-a')
        canonical = self.mapping.canonical()
        self.assertNotIn('reviewer', canonical)
        self.assertNotEqual(canonical['planner'], canonical['worker'])

    def test_value_equality_and_copy(self):
        self.mapping.assign('planner', 'planner-a')
        twin = copy.deepcopy(self.mapping)
        self.assertEqual(self.mapping, twin)
        other = RoleMapping({'planner': {'planner-a'}, 'worker': set(), 'reviewer': set()})
        self.assertNotEqual(twin, other)

    def test_constructor_rejects_unknown_role_candidates(self):
        with self.assertRaises(ValueError):
            RoleMapping({'planner': {'x'}, 'coordinator': {'y'}})

    def test_missing_role_candidate_set_is_empty(self):
        mapping = RoleMapping({'planner': {'p'}})
        self.assertEqual(mapping.candidates('worker'), frozenset())
        with self.assertRaises(ValueError):
            mapping.assign('worker', 'anything')


if __name__ == '__main__':
    unittest.main()