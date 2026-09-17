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


if __name__ == "__main__":
    unittest.main()
