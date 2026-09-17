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

        custom_catalog = InstructionCatalog([rule])
        report = audit_catalog(custom_catalog)
        self.assertFalse(report["valid"])
        self.assertTrue(any("cannot supersede itself" in err for err in report["errors"]))

    def test_supersession_cycle_rejected(self):
        """Directed cycles in supersession graph must be rejected in resolution and catalog audit."""
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

        custom_catalog = InstructionCatalog([rule_a, rule_b])
        report = audit_catalog(custom_catalog)
        self.assertFalse(report["valid"])
        self.assertTrue(any("Supersession cycle detected" in err for err in report["errors"]))

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


if __name__ == "__main__":
    unittest.main()
