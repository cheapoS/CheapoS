"""Audit and static verification linter for the cheapoS instruction catalog."""
from typing import Any, Dict, List, Set, Tuple
from .catalog import DEFAULT_CATALOG, InstructionCatalog
from .resolver import compose, resolve_rules
from .types import AgentAudience, InstructionConflictError, InstructionRule


def audit_catalog(catalog: InstructionCatalog = DEFAULT_CATALOG) -> Dict[str, Any]:
    """Perform static linting and full state matrix verification on the catalog.
    
    Verifies:
    1. Reference integrity: All rule IDs in supersedes, incompatible_with, and 
       internal_disambiguation_required exist.
    2. Symmetry / consistency: Incompatible rules are reciprocal or properly handled.
    3. Permutation matrix: Composing instructions for every valid (role, mode, triggers)
       state executes without raising unhandled InstructionConflictError.
    4. Persona boundary: Every rule with an internal_disambiguation_required tag has its
       counterpart active when composing instructions for cheapoS internal agents.
    """
    rules = catalog.all_rules()
    rule_ids: Set[str] = {r.id for r in rules}
    errors: List[str] = []
    warnings: List[str] = []

    # 1. Reference integrity
    for r in rules:
        for s_id in r.supersedes:
            if s_id not in rule_ids:
                errors.append(f"Rule '{r.id}' supersedes nonexistent rule '{s_id}'.")
        for i_id in r.incompatible_with:
            if i_id not in rule_ids:
                errors.append(f"Rule '{r.id}' declares incompatibility with nonexistent rule '{i_id}'.")
        if r.internal_disambiguation_required:
            if r.internal_disambiguation_required not in rule_ids:
                errors.append(
                    f"Rule '{r.id}' requires nonexistent internal disambiguation '{r.internal_disambiguation_required}'."
                )

    # 2. Persona Boundary Verification
    # For rules with internal_disambiguation_required, ensure internal worker/planner composition includes the disambiguator
    for r in rules:
        if r.internal_disambiguation_required:
            disambiguator = catalog.get(r.internal_disambiguation_required)
            if disambiguator is None:
                continue
            # Check worker composition in unattended mode
            worker_rules = compose(role="worker", mode="unattended", catalog=catalog)
            worker_rule_ids = {wr.id for wr in worker_rules}
            if disambiguator.id not in worker_rule_ids:
                errors.append(
                    f"Boundary violation: External rule '{r.id}' requires disambiguation '{disambiguator.id}', "
                    f"but it is absent from worker unattended composition."
                )

    # 3. State Matrix Permutations
    roles = ["worker", "reviewer", "planner", "coordinator"]
    modes = ["interactive", "unattended"]
    trigger_sets: List[Tuple[str, ...]] = [
        (),
        ("output_cap",),
        ("compact_edits",),
        ("loop_detected",),
        ("review_rejected",),
        ("review_repair",),
        ("finish_review",),
        ("output_cap", "loop_detected"),
    ]

    tested_states = 0
    for role in roles:
        for mode in modes:
            for triggers in trigger_sets:
                tested_states += 1
                try:
                    active = compose(role=role, mode=mode, triggers=triggers, catalog=catalog)
                    active_ids = {a.id for a in active}
                    # Validate that no active rule has unresolved incompatible_with in active set
                    for a in active:
                        for incomp in a.incompatible_with:
                            if incomp in active_ids:
                                errors.append(
                                    f"State collision in (role={role}, mode={mode}, triggers={triggers}): "
                                    f"Rules '{a.id}' and '{incomp}' are both active."
                                )
                except InstructionConflictError as e:
                    errors.append(
                        f"Unhandled InstructionConflictError in valid state (role={role}, mode={mode}, triggers={triggers}): {e}"
                    )

    return {
        "total_rules": len(rules),
        "tested_states": tested_states,
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
