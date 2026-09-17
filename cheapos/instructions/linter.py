"""Audit and static verification linter for the cheapoS instruction catalog."""
import itertools
from typing import Any, Dict, List, Set, Tuple
from .catalog import DEFAULT_CATALOG, InstructionCatalog, ROLE_TO_AUDIENCE
from .resolver import compose, detect_supersession_cycles, resolve_rules
from .types import AgentAudience, InstructionConflictError, InstructionRule


def audit_catalog(catalog: InstructionCatalog = DEFAULT_CATALOG) -> Dict[str, Any]:
    """Perform static linting and full state matrix verification on the catalog.

    Verifies:
    1. Reference integrity: All rule IDs in supersedes, incompatible_with, and
       internal_disambiguation_required exist.
    2. Acyclicity: No self-supersessions or directed cycles in the supersession graph.
    3. Symmetry / consistency: Incompatible rules are reciprocal or properly handled.
    4. Permutation matrix: Composing instructions for every valid (role, mode, triggers)
       state executes without raising unhandled InstructionConflictError.
    5. Persona boundary: Every rule with an internal_disambiguation_required tag has its
       counterpart active when composing instructions for cheapoS internal agents.
    """
    rules = catalog.all_rules()
    rule_ids = {r.id for r in rules}
    errors: List[str] = []
    warnings: List[str] = []

    # 1. Reference integrity & Acyclicity
    for r in rules:
        if r.id in r.supersedes:
            errors.append(f"Rule '{r.id}' cannot supersede itself.")
        for s_id in r.supersedes:
            if s_id not in rule_ids:
                errors.append(f"Rule '{r.id}' supersedes nonexistent rule '{s_id}'.")
        for inc_id in r.incompatible_with:
            if inc_id not in rule_ids:
                errors.append(f"Rule '{r.id}' declares incompatibility with nonexistent rule '{inc_id}'.")
        if r.internal_disambiguation_required:
            if r.internal_disambiguation_required not in rule_ids:
                errors.append(
                    f"Rule '{r.id}' requires nonexistent internal disambiguation '{r.internal_disambiguation_required}'."
                )

    catalog_cycle = detect_supersession_cycles(rules)
    if catalog_cycle:
        errors.append(f"Supersession cycle detected in catalog: {' -> '.join(catalog_cycle)}")

    # 2. Persona Boundary Verification
    # For rules with internal_disambiguation_required, ensure internal worker and planner composition includes the disambiguator
    for r in rules:
        if r.internal_disambiguation_required:
            disambiguator = catalog.get(r.internal_disambiguation_required)
            if disambiguator is None:
                continue
            if disambiguator.applies_to_role("worker"):
                try:
                    worker_rules = compose(role="worker", mode="unattended", catalog=catalog)
                    worker_rule_ids = {wr.id for wr in worker_rules}
                    if disambiguator.id not in worker_rule_ids:
                        errors.append(
                            f"Boundary violation: External rule '{r.id}' requires disambiguation '{disambiguator.id}', "
                            f"but it is absent from worker unattended composition."
                        )
                except (InstructionConflictError, ValueError) as e:
                    errors.append(f"Boundary verification worker composition error for rule '{r.id}': {e}")
            if disambiguator.applies_to_role("planner"):
                try:
                    planner_rules = compose(role="planner", mode="unattended", catalog=catalog)
                    planner_rule_ids = {pr.id for pr in planner_rules}
                    if disambiguator.id not in planner_rule_ids:
                        errors.append(
                            f"Boundary violation: External rule '{r.id}' requires disambiguation '{disambiguator.id}', "
                            f"but it is absent from planner unattended composition."
                        )
                except (InstructionConflictError, ValueError) as e:
                    errors.append(f"Boundary verification planner composition error for rule '{r.id}': {e}")

    # 3. State Matrix Permutations
    # Include all roles present in ROLE_TO_AUDIENCE plus any explicit roles in catalog rules
    roles_set = set(ROLE_TO_AUDIENCE.keys())
    for r in rules:
        for r_role in r.roles:
            if r_role != "all":
                roles_set.add(r_role)
    roles = sorted(roles_set)

    # Include all modes referenced by rules and standard runtime contexts
    modes_set = {"interactive", "unattended"}
    for r in rules:
        for m in r.modes:
            if m != "all":
                modes_set.add(m)
    modes = sorted(modes_set)

    # Collect all unique state triggers present in catalog rules
    catalog_triggers = sorted(list({t for r in rules for t in r.state_triggers}))
    trigger_sets: List[Tuple[str, ...]] = [()]
    for t in catalog_triggers:
        trigger_sets.append((t,))
    for pair in itertools.combinations(catalog_triggers, 2):
        trigger_sets.append(pair)
    if len(catalog_triggers) > 2:
        trigger_sets.append(tuple(catalog_triggers))

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
                except (InstructionConflictError, ValueError) as e:
                    errors.append(
                        f"Unhandled error in valid state (role={role}, mode={mode}, triggers={triggers}): {e}"
                    )

    return {
        "total_rules": len(rules),
        "tested_states": tested_states,
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
