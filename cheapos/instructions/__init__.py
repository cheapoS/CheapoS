"""cheapos instruction management and conflict prevention package."""
from .types import (
    AgentAudience,
    InstructionCategory,
    InstructionConflictError,
    InstructionRule,
)
from .catalog import DEFAULT_CATALOG, InstructionCatalog, RULES
from .resolver import (
    compose,
    compose_prompt,
    render_instructions,
    resolve_rules,
)
from .linter import audit_catalog

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
    "compose",
    "compose_prompt",
    "render_instructions",
    "resolve_rules",
    "audit_catalog",
    "ACTION_GUIDANCE",
    "OUTPUT_GUIDANCE",
    "COMPACT_GUIDANCE",
    "EDIT_RECOVERY_GUIDANCE",
]
