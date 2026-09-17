"""Resolver for composing instruction rules, eliminating superseded rules, and catching conflicts."""
import shlex
from typing import Any, List, Optional, Sequence, Set, Union
from .catalog import DEFAULT_CATALOG, InstructionCatalog, detect_supersession_cycles
from .types import AgentAudience, InstructionConflictError, InstructionRule


def _is_truthy(val: Any) -> bool:
    if val is True:
        return True
    if val is False or val is None:
        return False
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    return bool(val)


def _has_guidance_text(val: Any) -> bool:
    """Check if a guidance text field contains non-empty prose or explicit activation."""
    if val is True:
        return True
    if isinstance(val, str):
        cleaned = val.strip()
        return bool(cleaned) and cleaned.lower() not in ("false", "none", "null", "0")
    return False


def active_branch_item(task: dict) -> Optional[dict]:
    """Retrieve the currently active branch run item from task if present."""
    if not isinstance(task, dict):
        return None
    run = task.get("branch_run")
    if not isinstance(run, dict):
        return None
    current_id = run.get("current_item_id")
    items = run.get("items")
    if not isinstance(items, list):
        return None
    return next((i for i in items if isinstance(i, dict) and i.get("id") == current_id), None)


def is_command_authorized(task: dict, run: dict, command: Union[str, Sequence]) -> bool:
    """Check whether a specific test command is authorized for execution."""
    if task.get("full_suite_approved") is True or task.get("full_suite") is True:
        return True
    from cheapos import test_policy
    canonical = shlex.join(test_policy.argv(command))
    approval = task.get("full_suite_approval")
    if isinstance(approval, (list, tuple, set)) and canonical in approval:
        return True
    if isinstance(run, dict) and not run.get("test_policy_version") and run.get("authorization_ref"):
        plan = run.get("plan")
        if isinstance(plan, dict) and canonical in test_policy.plan_commands(plan):
            return True
    return False


def is_full_suite_authorized(task: dict) -> bool:
    """Check if task requires and is authorized for full-suite test execution in current item/phase."""
    if not isinstance(task, dict):
        return False

    from cheapos import test_policy

    run = task.get("branch_run")
    if isinstance(run, dict):
        item = active_branch_item(task)
        if item is not None and isinstance(item, dict):
            # Active item context: must check if this specific item requires a full suite
            checks = item.get("required_checks")
            if isinstance(checks, list):
                fs_checks = [c for c in checks if test_policy.full_suite(c)]
                if not fs_checks:
                    # Item requires only scoped/focused checks; approval for other items/phases
                    # does not mandate full suite during this item.
                    return False
                return any(is_command_authorized(task, run, c) for c in fs_checks)
            return task.get("full_suite_approved") is True or task.get("full_suite") is True

        # No active item: check if we are in final checks / review phase
        plan = run.get("plan") if isinstance(run.get("plan"), dict) else {}
        is_final_phase = (
            task.get("purpose") in ("branch_final", "final_checks", "final_review")
            or task.get("status") in ("final_review", "reviewing", "completed")
            or (
                isinstance(run.get("items"), list)
                and len(run.get("items")) > 0
                and all(i.get("status") in ("completed", "done", "merged", "reviewed") for i in run.get("items") if isinstance(i, dict))
            )
        )
        if is_final_phase:
            final_checks = plan.get("final_checks", [])
            if isinstance(final_checks, list):
                fs_final = [c for c in final_checks if test_policy.full_suite(c)]
                if not fs_final:
                    return False
                return any(is_command_authorized(task, run, c) for c in fs_final)

        # Plan-level fallback when no item is selected and not in final phase (e.g. plan preview/approval)
        if task.get("full_suite_approved") is True or task.get("full_suite") is True:
            return True
        approval = task.get("full_suite_approval")
        if isinstance(approval, (list, tuple, set)) and len(approval) > 0:
            return True
        if not run.get("test_policy_version") and run.get("authorization_ref"):
            if test_policy.plan_commands(plan):
                return True
        return False

    # Standalone task without branch_run
    if task.get("full_suite_approved") is True or task.get("full_suite") is True:
        return True
    if task.get("check_command"):
        if test_policy.full_suite(task["check_command"]):
            return is_command_authorized(task, {}, task["check_command"])
        return False
    approval = task.get("full_suite_approval")
    if isinstance(approval, (list, tuple, set)) and len(approval) > 0:
        return True
    return False


def resolve_rules(candidate_rules: Sequence[InstructionRule]) -> List[InstructionRule]:
    """Resolve a candidate set of rules by applying supersessions and checking conflicts.

    1. Checks candidate integrity: rejects duplicate IDs, self-supersessions, and cycles.
    2. Collects supersessions among active candidates and prunes superseded rules.
    3. Checks for mutual exclusions: if rule X declares incompatibility with rule Y, and
       both are present after pruning, raises InstructionConflictError.
    4. Orders rules deterministically by priority (descending) and ID (ascending).
    """
    seen_ids: Set[str] = set()
    rule_map = {}
    for r in candidate_rules:
        if r.id in seen_ids:
            raise ValueError(f"Duplicate instruction rule ID in candidate set: '{r.id}'")
        seen_ids.add(r.id)
        rule_map[r.id] = r

    for r in rule_map.values():
        if r.id in r.supersedes:
            raise ValueError(f"Rule '{r.id}' cannot supersede itself.")

    cycle = detect_supersession_cycles(candidate_rules)
    if cycle:
        raise ValueError(f"Supersession cycle detected: {' -> '.join(cycle)}")

    # Apply supersessions among active candidates
    superseded_ids: Set[str] = set()
    for r in rule_map.values():
        superseded_ids.update(r.supersedes)

    active_map = {r_id: r for r_id, r in rule_map.items() if r_id not in superseded_ids}

    # Conflict detection
    active_ids = set(active_map.keys())
    for r in active_map.values():
        for forbidden in r.incompatible_with:
            if forbidden in active_ids:
                raise InstructionConflictError(
                    f"Conflicting instructions detected: Rule '{r.id}' is incompatible with active rule '{forbidden}'.",
                    rule_ids=[r.id, forbidden]
                )

    # Sort deterministically by priority descending, then id ascending
    sorted_rules = sorted(active_map.values(), key=lambda r: (-r.priority, r.id))
    return sorted_rules


def render_instructions(rules: Sequence[InstructionRule], separator: str = "\n\n") -> str:
    """Render a sequence of instruction rules into a coherent prompt string."""
    return separator.join(r.text.strip() for r in rules if r.text.strip())


def compose(
    role: str = "worker",
    mode: str = "unattended",
    audience: Optional[AgentAudience] = None,
    triggers: Sequence[str] = (),
    catalog: InstructionCatalog = DEFAULT_CATALOG
) -> List[InstructionRule]:
    """Filter rules from catalog and resolve them into a coherent active instruction set."""
    candidates = catalog.filter(audience=audience, role=role, mode=mode, triggers=triggers)
    return resolve_rules(candidates)


def compose_prompt(
    role: str = "worker",
    mode: str = "unattended",
    audience: Optional[AgentAudience] = None,
    triggers: Sequence[str] = (),
    catalog: InstructionCatalog = DEFAULT_CATALOG
) -> str:
    """Compose and render prompt text directly."""
    rules = compose(role=role, mode=mode, audience=audience, triggers=triggers, catalog=catalog)
    return render_instructions(rules)


def triggers_for_task(task: dict) -> List[str]:
    """Extract active instruction triggers from a cheapoS task dict."""
    triggers: List[str] = []
    if not isinstance(task, dict):
        return triggers
    if _is_truthy(task.get("output_recovery")):
        triggers.append("output_cap")
    if _is_truthy(task.get("compact_edits")):
        triggers.append("compact_edits")
    if _is_truthy(task.get("action_pending")) or _has_guidance_text(task.get("loop_guidance")):
        triggers.append("loop_detected")
    if _is_truthy(task.get("finish_review")):
        triggers.append("finish_review")
    if is_full_suite_authorized(task):
        triggers.append("full_suite_requested")

    item = active_branch_item(task)
    run = task.get("branch_run") if isinstance(task.get("branch_run"), dict) else {}
    repair = (item.get("review_repair") if isinstance(item, dict) else None) or task.get("review_repair")
    ledger_findings = run.get("dispute_ledger", {}).get("findings", {}) if isinstance(run.get("dispute_ledger"), dict) else {}

    # Distinguish historical repair evidence from active unresolved defects
    repair_finding_ids = repair.get("finding_ids", []) if isinstance(repair, dict) else []
    if repair_finding_ids and ledger_findings:
        has_unresolved_repair = any(
            ledger_findings.get(fid, {}).get("status") != "independently_resolved"
            for fid in repair_finding_ids
        )
    elif repair and isinstance(repair, dict) and (repair.get("defects") or repair.get("candidate_id")):
        has_unresolved_repair = True
    else:
        has_unresolved_repair = False

    if has_unresolved_repair:
        triggers.append("review_repair")

    # Rejection guidance activates only for outstanding unresolved findings or active repair defects
    has_outstanding_disputes = _is_truthy(task.get("review_disputes")) or any(
        isinstance(f, dict) and f.get("status") != "independently_resolved"
        for f in ledger_findings.values()
    )
    if has_outstanding_disputes or (has_unresolved_repair and repair_finding_ids):
        triggers.append("review_rejected")

    return triggers


def rules_for_task(
    task: dict,
    role: str = "worker",
    catalog: InstructionCatalog = DEFAULT_CATALOG,
    extra_triggers: Sequence[str] = ()
) -> List[InstructionRule]:
    """Resolve active instruction rules for a runtime task dictionary."""
    from cheapos import execution_context
    mode = execution_context.mode(task, role=role) if isinstance(task, dict) else "unattended"
    triggers = list(triggers_for_task(task)) + list(extra_triggers)
    return compose(role=role, mode=mode, triggers=triggers, catalog=catalog)
