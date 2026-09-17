"""Resolver for composing instruction rules, eliminating superseded rules, and catching conflicts."""
from typing import List, Optional, Sequence, Set
from .catalog import DEFAULT_CATALOG, InstructionCatalog
from .types import AgentAudience, InstructionConflictError, InstructionRule


def detect_supersession_cycles(rules: Sequence[InstructionRule]) -> Optional[List[str]]:
    """Detect directed cycles in the supersession graph of candidate rules."""
    rule_ids = {r.id for r in rules}
    adj = {r.id: [s for s in r.supersedes if s in rule_ids] for r in rules}

    visited: Set[str] = set()
    rec_stack: List[str] = []
    rec_set: Set[str] = set()

    def dfs(node: str) -> Optional[List[str]]:
        visited.add(node)
        rec_stack.append(node)
        rec_set.add(node)
        for neighbor in adj.get(node, []):
            if neighbor in rec_set:
                cycle_start = rec_stack.index(neighbor)
                return rec_stack[cycle_start:] + [neighbor]
            if neighbor not in visited:
                found = dfs(neighbor)
                if found:
                    return found
        rec_stack.pop()
        rec_set.remove(node)
        return None

    for node in adj:
        if node not in visited:
            cycle = dfs(node)
            if cycle:
                return cycle
    return None


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


def triggers_for_task(task: dict) -> List[str]:
    """Extract active instruction triggers from a cheapoS task dict."""
    triggers: List[str] = []
    if not isinstance(task, dict):
        return triggers
    if task.get("output_recovery"):
        triggers.append("output_cap")
    if task.get("compact_edits"):
        triggers.append("compact_edits")
    if task.get("action_pending") or task.get("loop_guidance"):
        triggers.append("loop_detected")
    if task.get("finish_review"):
        triggers.append("finish_review")
    if task.get("full_suite_approved") or task.get("full_suite"):
        triggers.append("full_suite_requested")

    item = active_branch_item(task)
    run = task.get("branch_run") if isinstance(task.get("branch_run"), dict) else {}
    repair = (item.get("review_repair") if isinstance(item, dict) else None) or task.get("review_repair")

    if repair and isinstance(repair, dict) and (repair.get("defects") or repair.get("finding_ids") or repair.get("candidate_id")):
        triggers.append("review_repair")

    ledger_findings = run.get("dispute_ledger", {}).get("findings", {}) if isinstance(run.get("dispute_ledger"), dict) else {}
    unresolved_findings = any(
        isinstance(f, dict) and f.get("status") != "independently_resolved"
        for f in ledger_findings.values()
    )
    if task.get("review_disputes") or unresolved_findings or (repair and repair.get("finding_ids")):
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
    mode = execution_context.mode(task) if isinstance(task, dict) else "unattended"
    triggers = list(triggers_for_task(task)) + list(extra_triggers)
    return compose(role=role, mode=mode, triggers=triggers, catalog=catalog)
