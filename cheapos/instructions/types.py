"""Type definitions for the cheapoS instruction catalog and conflict detection system."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence, Tuple


class AgentAudience(str, Enum):
    EXTERNAL_HOST = "external_host"        # External IDE/CLI developer (Antigravity, Claude Code, Cursor)
    CHEAPOS_WORKER = "cheapos_worker"      # Internal cheapoS worker / chat agent
    CHEAPOS_PLANNER = "cheapos_planner"    # Internal cheapoS planner
    CHEAPOS_REVIEWER = "cheapos_reviewer"  # Internal cheapoS senior reviewer
    CHEAPOS_COORDINATOR = "cheapos_coordinator"  # Internal recovery coordinator
    ALL = "all"


class InstructionCategory(str, Enum):
    SAFETY = "safety"
    GIT = "git"
    TDD = "tdd"
    VALIDATION = "validation"
    WORKFLOW = "workflow"
    RECOVERY = "recovery"
    COORDINATION = "coordination"


class InstructionConflictError(ValueError):
    """Raised when mutually exclusive or contradictory instructions are composed together."""
    def __init__(self, message: str, rule_ids: Sequence[str] = ()):
        super().__init__(message)
        self.rule_ids = list(rule_ids)


@dataclass(frozen=True)
class InstructionRule:
    """A structured, auditable instruction or behavioral constraint for an agent."""
    id: str
    audience: AgentAudience
    category: InstructionCategory
    text: str
    roles: Tuple[str, ...] = ("all",)
    modes: Tuple[str, ...] = ("all",)
    state_triggers: Tuple[str, ...] = ()
    rationale: str = ""
    supersedes: Tuple[str, ...] = ()
    incompatible_with: Tuple[str, ...] = ()
    internal_disambiguation_required: str = ""
    priority: int = 50

    def applies_to_role(self, role: str) -> bool:
        return "all" in self.roles or role in self.roles

    def applies_to_mode(self, mode: str) -> bool:
        return "all" in self.modes or mode in self.modes

    def applies_to_triggers(self, active_triggers: Sequence[str]) -> bool:
        if not self.state_triggers:
            return True
        return any(t in active_triggers for t in self.state_triggers)
