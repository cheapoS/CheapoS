# Runtime instruction audit

Audited 2026-09-22 against the actual prompt producers and request boundary.
The catalog existed, but only six recovery/setup constants were wired to it.
The generic role/mode resolver and its conflict tests therefore did not describe
all instructions reaching a model. Passing that lint was not proof of runtime
consistency.

## Findings and corrections

| Finding | Correction |
| --- | --- |
| Worker, chat, planner, reviewer and coordinator system text lived separately from the catalog. | Active entry points now use registered catalog entries and explicit runtime profiles. Shared evidence, disagreement, publication, command and stage guidance uses catalog lookups. |
| Catalog chat guidance forbade code examples while the conversation implementation explicitly allowed them. | The canonical chat rule permits examples during discussion and requires file tools for requested implementation. Discussion remains read-only. |
| Catalog validation/planner rules imposed a universal two-second test requirement. | Guidance follows the captured repository policy and actual authorization. A required check cannot be silently replaced with weaker coverage. These old catalog rules were not themselves the active runtime planner policy. |
| Reviewer escalation prose promised an unconditional approval pause, despite controller-specific recovery paths. | Guidance leaves recovery to the controller and grants no model, command or budget changes. Decision values still come from each phase's schema. |
| Unattended worker prompts were made by replacing a sentence in the interactive commit policy. | Explicit worker/interactive/unattended profiles select the appropriate Git and clarification policy. No prose matching selects authority. |
| Unattended policy was repeated during final request assembly. | The current worker profile is refreshed once; active-item evidence stays separate. |
| Interactive saved system messages could remain stale, and planner instructions refreshed only on a contract-version change. | Worker dispatch and planner Resume refresh the controller-owned opening policy without resetting observations, messages, attempts, pending proposals or grants. |
| Tool availability changed during review corrections and other phases, while prose could still refer to general tools. | Each outgoing request receives one current tool contract derived from its actual schemas, decision enums and forced-call choice. It is refreshed after prompt assembly and before request reservation/transport. |
| Tests mainly established catalog consistency or constant parity. | Small regressions exercise real provider-boundary assembly, saved planning Resume, role tool sets and review correction/final-review requests. A source check rejects new inline primary prompts. |
| Every criterion required implementation evidence, including criteria solely about a captured command result. | `reviewer.assessment` distinguishes the controller-listed command-result criteria. Their schemas and evidence catalog name exact current check receipts; behavioral and regression claims still need source/visual evidence. Item Resume refreshes the mapping without resetting reads/attempts; paged final synthesis keeps receipts available through the evidence reader. |
| Requests without an initial system message duplicated the tool contract when assembled again for transport. | Refresh recognizes both appended and standalone contracts. Provider-boundary failover coverage requires one current contract plus the unchanged saved evidence. |

The preceding evidence-recovery fix supplies reusable citations, preserves
same-candidate evidence across reviewer handoffs, and keeps saved-evidence reads
available during decision coaching. This audit centralizes its prose; it does
not replace its provenance checks or grant an approval.

## Runtime entry points

`cheapos/instructions/catalog.py` is the canonical policy registry.
`cheapos/instructions/runtime.py` selects explicit profiles and applies the
existing supersession/conflict resolver to their registered rules. A runtime
profile is a deliberate selection, not the union of every rule for a role.
This matters for a final reviewer, a conversational reply and a recovery
coordinator, which have different tools and output contracts.

| Runtime entry point | Catalog profile or rules |
| --- | --- |
| Worker system, including restarted/handoff requests | `worker`, `interactive`, `unattended`; scoped validation and command policy |
| Finish review and worker stages | `recovery.finish_review`, `stage.*` |
| Opening chat / connection greeting | `greeting`, `startup_greeting` |
| Discussion during an existing task | `discussion` |
| Proposal planning, including Resume | `planner` |
| Checkpoint / unattended item review | `reviewer`, `reviewer.item_*` |
| Review correction / decision coaching | `review_reassessment`, `review_decision_coaching` |
| Final packet, page and synthesis review | `final_review`, current coverage data and `reviewer.original_scope` |
| Evidence reads / citation correction | `reviewer.assessment`, `reviewer.evidence_catalog`, `reviewer.delivered_excerpt`, `reviewer.correct_citation` |
| Review findings / worker repair | `reviewer.defects`, `recovery.disagreement` |
| Recovery coordinator / local chat delegation | `coordinator_recovery`, `coordinator_chat` |
| PR metadata | `publication.worker`, `publication.review`, `publication.final` |

Tool definitions remain with the controller. The tool contract reports the
already-selected tools; it never adds tools, runs checks, expands permissions,
changes routes or approves work. Read-only turns remain read-only. Connection
probes retain their exact small protocol rather than receiving task policies.
The request-local contract is not appended to durable conversation history.

## What remains local to producers

Current task IDs, criteria, file inventory, returned evidence, command results,
coverage arguments and exact validation errors remain with the code producing
them. These are facts or schema-specific diagnostics, not a second source of
shared role policy. Tool descriptions stay next to the corresponding schema.
Captured repository guidance and operator messages retain their original text
and authority; this change does not rewrite them into catalog rules.

Generic `compose`/`rules_for_task` remain available for catalog policy audits.
They are not a substitute for the explicit runtime profiles or provider-boundary
tests. The linter detects declared incompatibilities; it does not understand
every possible contradiction in natural-language instructions.

## Keeping it covered

Follow the instruction-change rule in `AGENTS.md`. Register shared policy, use
an explicit profile or catalog lookup, and update this entry-point inventory.
For changed tools, check the final assembled prompt and exact offered schemas
in the affected phase, including recovery and Resume. Do not solve mismatches by
silently granting additional tools or disabling verification.

Focused offline checks:

```sh
python3 -B -m unittest tests.test_runtime_instructions tests.test_instructions
python3 -B -m unittest tests.test_planner_inspection_recovery tests.test_branch_review_recovery tests.test_final_review_history
```

The new tests use in-memory providers and existing small fixtures, without Git
workflows, network requests or real-time waits. These checks demonstrate prompt
wiring and preservation of authority/state. They do not establish that a live
model will interpret every instruction correctly, produce a good review or
finish in fewer calls. Live task outcomes still need observation.
