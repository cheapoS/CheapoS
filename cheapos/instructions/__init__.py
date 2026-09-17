"""cheapos instruction management and conflict prevention package."""
from .types import (
    AgentAudience,
    InstructionCategory,
    InstructionConflictError,
    InstructionRule,
)
from .catalog import DEFAULT_CATALOG, InstructionCatalog, RULES
from .resolver import (
    active_branch_item,
    compose,
    compose_prompt,
    is_full_suite_authorized,
    render_instructions,
    resolve_rules,
    rules_for_task,
    triggers_for_task,
)
from .linter import audit_catalog, probe_context_matrix

# Canonical guidance strings backed by the catalog
ACTION_GUIDANCE = DEFAULT_CATALOG.get("recovery.action_guidance").text
OUTPUT_GUIDANCE = DEFAULT_CATALOG.get("recovery.output_cap").text
COMPACT_GUIDANCE = DEFAULT_CATALOG.get("recovery.compact_edits").text
EDIT_RECOVERY_GUIDANCE = "\n" + DEFAULT_CATALOG.get("recovery.edit_guidance").text

__all__ = [
    "AgentAudience",
    "InstructionCategory",
    "InstructionConflictError",
    "InstructionRule",
    "InstructionCatalog",
    "DEFAULT_CATALOG",
    "RULES",
    "active_branch_item",
    "compose",
    "compose_prompt",
    "is_full_suite_authorized",
    "render_instructions",
    "resolve_rules",
    "rules_for_task",
    "triggers_for_task",
    "audit_catalog",
    "probe_context_matrix",
    "ACTION_GUIDANCE",
    "OUTPUT_GUIDANCE",
    "COMPACT_GUIDANCE",
    "EDIT_RECOVERY_GUIDANCE",
]
