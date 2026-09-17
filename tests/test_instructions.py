"""Unit tests for cheapoS instruction catalog, resolver, and conflict linter."""
import unittest

from cheapos.instructions import (
    AgentAudience,
    InstructionCategory,
    InstructionConflictError,
    InstructionCatalog,
    InstructionRule,
    audit_catalog,
    compose,
    compose_prompt,
    resolve_rules,
)


class InstructionCatalogTests(unittest.TestCase):

    def test_audit_catalog_passes_cleanly(self):
        """The default instruction catalog must pass all reference and matrix audits."""
        report = audit_catalog()
        self.assertTrue(report["valid"], f"Catalog audit failed: {report['errors']}")
        self.assertEqual(report["errors"], [])
        self.assertGreaterEqual(report["tested_states"], 40)
        self.assertGreaterEqual(report["total_rules"], 10)

    def test_conflict_detection_raises_error(self):
        """Combining mutually incompatible rules without supersession must fail fast."""
        rule_a = InstructionRule(
            id="test.rule_a",
            audience=AgentAudience.ALL,
            category=InstructionCategory.VALIDATION,
            text="Rule A directive.",
            incompatible_with=("test.rule_b",),
        )
        rule_b = InstructionRule(
            id="test.rule_b",
            audience=AgentAudience.ALL,
            category=InstructionCategory.VALIDATION,
            text="Rule B directive.",
            incompatible_with=("test.rule_a",),
        )
        with self.assertRaises(InstructionConflictError) as ctx:
            resolve_rules([rule_a, rule_b])
        self.assertIn("test.rule_a", ctx.exception.rule_ids)
        self.assertIn("test.rule_b", ctx.exception.rule_ids)

    def test_supersession_resolves_conflict(self):
        """A rule declaring supersession removes the superseded rule before conflict checking."""
        rule_old = InstructionRule(
            id="git.manual_commit",
            audience=AgentAudience.EXTERNAL_HOST,
            category=InstructionCategory.GIT,
            text="Manually run git commit.",
            incompatible_with=("git.controller_commit",),
        )
        rule_new = InstructionRule(
            id="git.controller_commit",
            audience=AgentAudience.CHEAPOS_WORKER,
            category=InstructionCategory.GIT,
            text="Controller manages commits automatically.",
            supersedes=("git.manual_commit",),
            incompatible_with=("git.manual_commit",),
        )
        resolved = resolve_rules([rule_old, rule_new])
        resolved_ids = [r.id for r in resolved]
        self.assertEqual(resolved_ids, ["git.controller_commit"])

    def test_worker_unattended_composition(self):
        """Worker in unattended mode receives controller commit rule and autonomous policy."""
        rules = compose(role="worker", mode="unattended")
        rule_ids = {r.id for r in rules}
        self.assertIn("git.internal.controller_owns_commits", rule_ids)
        self.assertNotIn("git.external.commit_on_finish", rule_ids)
        self.assertIn("workflow.unattended_policy", rule_ids)
        self.assertIn("tdd.inspect_and_establish_tests", rule_ids)
        self.assertIn("core.untrusted_evidence", rule_ids)

        prompt = compose_prompt(role="worker", mode="unattended")
        self.assertIn("controller owns branch commits", prompt)
        self.assertIn("test-driven discipline", prompt)
        self.assertNotIn("stage and commit your work before handing the project back", prompt)

    def test_worker_interactive_composition(self):
        """Worker in interactive mode receives conversational framing and UI commit guidance."""
        rules = compose(role="worker", mode="interactive")
        rule_ids = {r.id for r in rules}
        self.assertIn("git.internal.interactive_commit_guidance", rule_ids)
        self.assertIn("workflow.chat_base", rule_ids)
        self.assertNotIn("workflow.unattended_policy", rule_ids)

    def test_reviewer_composition(self):
        """Reviewer receives inspection and decision rules without worker edit rules."""
        rules = compose(role="reviewer")
        rule_ids = {r.id for r in rules}
        self.assertIn("reviewer.base", rule_ids)
        self.assertIn("reviewer.decisions", rule_ids)
        self.assertNotIn("workflow.worker_base", rule_ids)

    def test_planner_composition_includes_shared_git_and_setup_rules(self):
        """Planner composition must include internal controller commit rules and unattended setup policy."""
        rules = compose(role="planner", mode="unattended")
        rule_ids = {r.id for r in rules}
        self.assertIn("git.internal.controller_owns_commits", rule_ids)
        self.assertIn("workflow.unattended_setup_policy", rule_ids)
        self.assertIn("planner.base", rule_ids)
        self.assertIn("core.untrusted_evidence", rule_ids)
        self.assertIn("validation.change_scoped", rule_ids)
        self.assertNotIn("workflow.worker_base", rule_ids)
        self.assertNotIn("reviewer.base", rule_ids)

    def test_trigger_activates_recovery_guidance(self):
        """Specifying triggers activates conditional recovery rules."""
        # Baseline without trigger
        normal = compose(role="worker", mode="unattended")
        normal_ids = {r.id for r in normal}
        self.assertNotIn("recovery.output_cap", normal_ids)

        # With trigger
        recovered = compose(role="worker", mode="unattended", triggers=["output_cap"])
        recovered_ids = {r.id for r in recovered}
        self.assertIn("recovery.output_cap", recovered_ids)

    def test_compact_edits_supersedes_output_cap(self):
        """When both output_cap and compact_edits triggers fire, compact_edits takes precedence."""
        combined = compose(role="worker", mode="unattended", triggers=["output_cap", "compact_edits"])
        combined_ids = {r.id for r in combined}
        self.assertIn("recovery.compact_edits", combined_ids)
        self.assertNotIn("recovery.output_cap", combined_ids)
        prompt = compose_prompt(role="worker", mode="unattended", triggers=["output_cap", "compact_edits"])
        self.assertIn("replace_text is unavailable in this recovery", prompt)
        self.assertNotIn("prefer a short exact replace_text", prompt)

    def test_boundary_firewall_audit(self):
        """Linter must detect when an external rule lacks required internal disambiguation."""
        bad_rule = InstructionRule(
            id="bad.external_rule",
            audience=AgentAudience.EXTERNAL_HOST,
            category=InstructionCategory.GIT,
            text="External rule text.",
            internal_disambiguation_required="nonexistent.override",
        )
        custom_catalog = InstructionCatalog([bad_rule])
        report = audit_catalog(custom_catalog)
        self.assertFalse(report["valid"])
        self.assertTrue(any("nonexistent.override" in err for err in report["errors"]))

    def test_rules_for_task(self):
        """rules_for_task resolves mode and triggers directly from runtime task dictionaries."""
        from cheapos.instructions import rules_for_task, triggers_for_task

        task_unattended = {
            "conversational": True,
            "branch_run": {"authorization_ref": {"id": "grant_1"}},
            "output_recovery": True,
        }
        triggers = triggers_for_task(task_unattended)
        self.assertIn("output_cap", triggers)

        rules = rules_for_task(task_unattended, role="worker")
        rule_ids = {r.id for r in rules}
        self.assertIn("workflow.unattended_policy", rule_ids)
        self.assertIn("recovery.output_cap", rule_ids)
        self.assertIn("git.internal.controller_owns_commits", rule_ids)

        task_interactive = {"conversational": True}
        rules_interactive = rules_for_task(task_interactive, role="worker")
        interactive_ids = {r.id for r in rules_interactive}
        self.assertIn("workflow.chat_base", interactive_ids)
        self.assertNotIn("workflow.unattended_policy", interactive_ids)

    def test_triggers_for_task_extracts_nested_review_repair_and_disputes(self):
        """Review repair and dispute triggers must be derived from active branch item and dispute ledger."""
        from cheapos.instructions import rules_for_task, triggers_for_task

        task = {
            "conversational": True,
            "branch_run": {
                "current_item_id": "item-2",
                "items": [
                    {"id": "item-1", "title": "Done item"},
                    {
                        "id": "item-2",
                        "title": "Repair item",
                        "review_repair": {
                            "candidate_id": "cand_1",
                            "defects": [{"finding_id": "find_1", "criterion": "crit"}],
                            "finding_ids": ["find_1"],
                        },
                    },
                ],
                "dispute_ledger": {
                    "findings": {
                        "find_1": {"id": "find_1", "status": "requested"},
                    }
                },
            },
        }
        triggers = triggers_for_task(task)
        self.assertIn("review_repair", triggers)
        self.assertIn("review_rejected", triggers)

        rules = rules_for_task(task, role="worker")
        rule_ids = {r.id for r in rules}
        self.assertIn("recovery.review_repair", rule_ids)
        self.assertIn("recovery.disagreement", rule_ids)

    def test_self_supersession_rejected(self):
        """A rule cannot supersede itself in resolution or catalog audit."""
        rule = InstructionRule(
            id="rule.self",
            audience=AgentAudience.CHEAPOS_INTERNAL,
            category=InstructionCategory.WORKFLOW,
            text="Self loop rule",
            supersedes=("rule.self",),
        )
        with self.assertRaises(ValueError) as ctx:
            resolve_rules([rule])
        self.assertIn("cannot supersede itself", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            InstructionCatalog([rule])
        self.assertIn("cannot supersede itself", str(ctx.exception))

        custom_catalog = InstructionCatalog([rule], validate=False)
        report = audit_catalog(custom_catalog)
        self.assertFalse(report["valid"])
        self.assertTrue(any("cannot supersede itself" in err for err in report["errors"]))

    def test_supersession_cycle_rejected(self):
        """Directed cycles in supersession graph must be rejected in resolution, construction, and catalog audit."""
        rule_a = InstructionRule(
            id="rule.a",
            audience=AgentAudience.CHEAPOS_INTERNAL,
            category=InstructionCategory.WORKFLOW,
            text="Rule A",
            supersedes=("rule.b",),
        )
        rule_b = InstructionRule(
            id="rule.b",
            audience=AgentAudience.CHEAPOS_INTERNAL,
            category=InstructionCategory.WORKFLOW,
            text="Rule B",
            supersedes=("rule.a",),
        )
        with self.assertRaises(ValueError) as ctx:
            resolve_rules([rule_a, rule_b])
        self.assertIn("Supersession cycle detected", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            InstructionCatalog([rule_a, rule_b])
        self.assertIn("Supersession cycle detected", str(ctx.exception))

        custom_catalog = InstructionCatalog([rule_a, rule_b], validate=False)
        report = audit_catalog(custom_catalog)
        self.assertFalse(report["valid"])
        self.assertTrue(any("Supersession cycle detected" in err for err in report["errors"]))

    def test_invalid_selectors_rejected_at_construction(self):
        """Rules declaring invalid roles, modes, audience, or category must be rejected at catalog construction."""
        # Invalid role
        bad_role_rule = InstructionRule(
            id="rule.bad_role",
            audience=AgentAudience.CHEAPOS_INTERNAL,
            category=InstructionCategory.WORKFLOW,
            roles=("nonexistent_role",),
            text="Bad role",
        )
        with self.assertRaises(ValueError) as ctx:
            InstructionCatalog([bad_role_rule])
        self.assertIn("invalid role selector", str(ctx.exception))

        # Invalid mode
        bad_mode_rule = InstructionRule(
            id="rule.bad_mode",
            audience=AgentAudience.CHEAPOS_INTERNAL,
            category=InstructionCategory.WORKFLOW,
            modes=("quantum_mode",),
            text="Bad mode",
        )
        with self.assertRaises(ValueError) as ctx:
            InstructionCatalog([bad_mode_rule])
        self.assertIn("invalid mode selector", str(ctx.exception))

        # Invalid audience
        bad_audience_rule = InstructionRule(
            id="rule.bad_audience",
            audience="not_an_audience",  # type: ignore
            category=InstructionCategory.WORKFLOW,
            text="Bad audience",
        )
        with self.assertRaises(ValueError) as ctx:
            InstructionCatalog([bad_audience_rule])
        self.assertIn("invalid audience selector", str(ctx.exception))

        # Invalid category
        bad_cat_rule = InstructionRule(
            id="rule.bad_category",
            audience=AgentAudience.CHEAPOS_INTERNAL,
            category="not_a_category",  # type: ignore
            text="Bad category",
        )
        with self.assertRaises(ValueError) as ctx:
            InstructionCatalog([bad_cat_rule])
        self.assertIn("invalid category selector", str(ctx.exception))

    def test_permutation_invariant_catalog_and_resolution(self):
        """Catalog inspection, filtering, and resolution must produce identical results regardless of input order."""
        import random
        rules = [
            InstructionRule(id="rule.p10", audience=AgentAudience.CHEAPOS_INTERNAL, category=InstructionCategory.WORKFLOW, priority=10, text="P10"),
            InstructionRule(id="rule.p50", audience=AgentAudience.CHEAPOS_INTERNAL, category=InstructionCategory.WORKFLOW, priority=50, text="P50"),
            InstructionRule(id="rule.p80", audience=AgentAudience.CHEAPOS_INTERNAL, category=InstructionCategory.WORKFLOW, priority=80, text="P80"),
            InstructionRule(id="rule.p90a", audience=AgentAudience.CHEAPOS_INTERNAL, category=InstructionCategory.WORKFLOW, priority=90, text="P90A"),
            InstructionRule(id="rule.p90b", audience=AgentAudience.CHEAPOS_INTERNAL, category=InstructionCategory.WORKFLOW, priority=90, text="P90B"),
        ]
        canonical_resolution = [r.id for r in resolve_rules(rules)]
        canonical_catalog = InstructionCatalog(rules)
        canonical_all = [r.id for r in canonical_catalog.all_rules()]
        canonical_filtered = [r.id for r in canonical_catalog.filter(role="worker")]

        rng = random.Random(42)
        for _ in range(25):
            shuffled = list(rules)
            rng.shuffle(shuffled)

            # Test resolve_rules permutation-invariance
            shuffled_resolution = [r.id for r in resolve_rules(shuffled)]
            self.assertEqual(canonical_resolution, shuffled_resolution)

            # Test catalog permutation-invariance
            cat = InstructionCatalog(shuffled)
            self.assertEqual(canonical_all, [r.id for r in cat.all_rules()])
            self.assertEqual(canonical_filtered, [r.id for r in cat.filter(role="worker")])

    def test_duplicate_rule_id_rejected(self):
        """Duplicate rule IDs must be rejected at catalog construction and in candidate set."""
        rule1 = InstructionRule(
            id="rule.dup",
            audience=AgentAudience.CHEAPOS_INTERNAL,
            category=InstructionCategory.WORKFLOW,
            text="First rule",
        )
        rule2 = InstructionRule(
            id="rule.dup",
            audience=AgentAudience.CHEAPOS_INTERNAL,
            category=InstructionCategory.WORKFLOW,
            text="Second rule with same ID",
        )
        # Rejection in candidate set
        with self.assertRaises(ValueError) as ctx:
            resolve_rules([rule1, rule2])
        self.assertIn("Duplicate instruction rule ID in candidate set", str(ctx.exception))

        # Rejection in catalog construction
        with self.assertRaises(ValueError) as ctx:
            InstructionCatalog([rule1, rule2])
        self.assertIn("Duplicate instruction rule ID detected in catalog", str(ctx.exception))

    def test_audit_matrix_covers_all_roles_and_compound_triggers(self):
        """Catalog audit must cover all roles in ROLE_TO_AUDIENCE, reachable modes, and pairwise triggers."""
        report = audit_catalog()
        self.assertTrue(report["valid"])
        # With 5 roles, 2 modes, and 30 trigger sets, at least 300 states are checked
        self.assertGreaterEqual(report["tested_states"], 300)

        # Compound trigger test: full suite requested combined with output cap and compact edits
        compound_rules = compose(
            role="worker",
            mode="unattended",
            triggers=["full_suite_requested", "output_cap", "compact_edits"],
        )
        compound_ids = {r.id for r in compound_rules}
        self.assertIn("validation.full_suite_mandatory", compound_ids)
        self.assertNotIn("validation.change_scoped", compound_ids)
        self.assertIn("recovery.compact_edits", compound_ids)
        self.assertNotIn("recovery.output_cap", compound_ids)


if __name__ == "__main__":
    unittest.main()
