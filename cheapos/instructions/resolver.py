"""Resolver for composing instruction rules, eliminating superseded rules, and catching conflicts."""
from typing import List, Optional, Sequence, Set
from .catalog import DEFAULT_CATALOG, InstructionCatalog
from .types import AgentAudience, InstructionConflictError, InstructionRule


def resolve_rules(candidate_rules: Sequence[InstructionRule]) -> List[InstructionRule]:
    """Resolve a candidate set of rules by applying supersessions and checking conflicts.
    
    1. Collects supersessions: if any rule supersedes other rules, those are pruned.
    2. Checks for mutual exclusions: if rule X declares incompatibility with rule Y, and
       both are present after pruning, raises InstructionConflictError.
    3. Orders rules deterministically by priority (descending) and ID (ascending).
    """
    rule_map = {r.id: r for r in candidate_rules}
    
    # Apply supersessions
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
