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
| Final review required a tool call but sent `tool_choice: auto`, allowing reasoning-only replies that could never advance the controller. | Final packet, item-packet and synthesis requests now require one of their offered tools at the provider boundary. Readers and both review decisions remain available; the catalog contract reflects that requirement. Correction, handoff and Resume rebuild the same request without approving missing evidence or forcing a verdict. |
| Some providers returned several evidence reads despite the serial-call preference; final review rejected all of them. | Offered read-only calls can now be processed as a durable batch with paired receipts. Decisions must arrive separately after the results, and mixed/unoffered batches execute nothing. Existing tool inventory, candidate binding and approval validation remain unchanged. |
| Tests mainly established catalog consistency or constant parity. | Small regressions exercise real provider-boundary assembly, saved planning Resume, role tool sets and review correction/final-review requests. A source check rejects new inline primary prompts. |
| Every criterion required implementation evidence, including criteria solely about a captured command result. | `reviewer.assessment` distinguishes the controller-listed command-result criteria. Their schemas and evidence catalog name exact current check receipts; behavioral and regression claims still need source/visual evidence. Item Resume refreshes the mapping without resetting reads/attempts; paged final synthesis keeps receipts available through the evidence reader. |
| Requests without an initial system message duplicated the tool contract when assembled again for transport. | Refresh recognizes both appended and standalone contracts. Provider-boundary failover coverage requires one current contract plus the unchanged saved evidence. |
| Styling reminders depended on operator prompts and reviewer-only prose. | Shared `workflow.ui_completeness` reaches Interactive/Unattended workers and item/final reviewers. It requires checking how markup uses existing styles, adding needed styling, and distinguishing rendered evidence from static inspection. Existing styles can justify no CSS edit; missing selector names alone cannot justify a regression. |

The preceding evidence-recovery fix supplies reusable citations, preserves
same-candidate evidence across reviewer handoffs, and keeps saved-evidence reads
available during decision coaching. This audit centralizes its prose; it does
not replace its provenance checks or grant an approval.

Uncapped item review now continues selecting the existing `review_reassessment`
profile after the usual investigation window. The nudge stays at the end of the
outgoing request once, while all authorized read tools remain available; it is
not a new work cap or an instruction to approve. The in-memory recovery tests
inspect these assembled messages and tool sets beyond eight distinct reads.
Repeated-read detection survives Resume and compares individual results across
different batches, ignoring only web cache/fetch-time metadata. The existing
authorized reviewer handoff then retains evidence and reaches a validated
decision. Older complete exchanges are retained through `read_context_evidence`
while both live and saved history use the same size bound; the evidence catalog
refreshes each request so an omitted exchange does not hide its source IDs.

## Durable final review profile

Evidence-enabled final requirement/integration units select `review_unit`, with
`reviewer.unit` and shared `workflow.ui_completeness`. The controller supplies
coverage; models return explicit judgments with delivered evidence handles. The
tool set retains exact-candidate/source/check readers and provisional records.
Small complete units have the same evidence obligations as the combined large
workflow. Independent identity and readiness gates remain outside model control.

`test_review_units` inspects actual prompts, tools, forced-tool dispatch and
non-accumulation through correction, JSON Resume and automatic handoff. It reaches
validated composition, tests integration rejection after requirement approval,
and preserves the old recovery history while sharing new protocol failures across
units. Legacy item/Interactive/read-only profiles remain unchanged and retain
their existing request-boundary coverage. See the
[design record](durable-review-workflow.md) for the protocol and research basis.

## Runtime entry points

Worker repeated-read notices select registered `recovery.repeated_read_work` or
`recovery.repeated_read_research` from the active item and existing work policy.
Implementation and repair keep their checkpoint objective; read-only questions
keep their answer objective and existing tools. Before dispatch, legacy notices
are retained by reference and replaced by one current direction. New evidence,
successful edits or completed verification clear that read notice without
clearing other recovery guidance, attempts, operator directions or check receipts.
Compaction refreshes the direction again so its base and tail cannot duplicate it.

Initial, action, repair and compacted worker snapshots select recent activity
from explicit current-item event ownership, with an item-start boundary for
legacy untagged events. Unowned older events are not current-item work. Completed
items remain historical summaries and the original journal remains intact.
Interactive follow-ups keep bounded prior replies, actions and current snapshots
of previously read files. The latest user-message boundary limits current-request
observations, not conversation memory. Historical claims do not become passing
checks or review approval. The existing chat-continuity test exercises the actual
follow-up request and reconstruction from saved state alongside item-isolation tests.
The catalog's `recovery.working_memory` rule distinguishes the snapshot's patch
from the historical versions in action/check receipts. Small in-memory tests
inspect initial/action snapshots and provider-boundary requests across JSON
Resume, compaction and handoff, including read-only authority and tool pairing.

Item review selects the registered `review_progress` profile when the evidence
contract is enabled. Its `record_review_progress` tool validates one assessment
with the same claim validator used by final approval, then returns the remaining
questions. Decision coaching retains this tool alongside saved-evidence reads.
Current source IDs and recorded assessments refresh in every outgoing item
request. The successor reviewer receives provisional claims and must explicitly
confirm them; recording every target never creates an approval receipt.
Interactive checkpoint and partial chunk review retain their full assessment
contract. Final synthesis now selects the explicit final_review_progress profile
and offers incremental records, as documented below.

The basis includes candidate, criteria, command-receipt bindings and current
operator directions. Missing or changed evidence cannot be confirmed. Small
in-memory cases inspect offered tools and assembled prompts across Resume,
invalid confirmation and handoff, then reach an ordinary validated receipt.
Separate cases retain a complete checklist through cancellation without approval.
Single-label command-result criteria such as `Components tests passed (npm test)`
can cite the exact matching receipt; mixed behavioral clauses remain excluded.
Missing named receipts are shown explicitly: a validator's unit tests do not
prove it ran against the current inputs. If the reviewer requests that check,
the next review binds its actual worker-executed receipt, including for legacy
plans whose required-check list omitted it. No command is executed from criterion
prose, and ambiguous captured working directories remain unresolved.
Final synthesis also binds a result-only named check (for example, "The schema
check passes") to the same approved item's sole required command and directory.
Multiple checks or mixed behavioral claims remain unresolved by this rule.
The outgoing decision schema refreshes after saved proof is restored, outside
the packet binding, so upgrading does not discard reads, completed packets or
attempt history. The small saved-review fixture checks the actual tool schema
through Resume and a reviewer handoff to a validated decision.
Final-review continuation also bounds the actual outgoing conversation to its
saved complete exchanges. Omitted exchanges remain retrievable through the
existing context reader. A compact current correction survives oversized rejected
verdicts; it is request data outside the packet binding, not new authority or
approval. Deterministic request-boundary tests cover continued review and
Resume/handoff through a valid decision, with evidence, attempts and check
receipts retained and no accumulating continuation messages.
An omitted source-ID prefix resolves only when its full 20-character suffix
matches one current source, and returns that source's canonical citation.
The shared citation validator distinguishes a valid delivered excerpt ID with an
invalid optional quote from missing or stale evidence. Its registered
`reviewer.correct_quote` diagnostic returns the verified citation object and asks
for an explicit corrected response; it never accepts the bad quote automatically.
The final-review request-boundary fixture receives that correction and completes
without another read. Shared validator tests keep fabricated, mismatched and
stale references rejected without manufacturing replacement citations.

Planning requires commands explicitly promised by acceptance criteria to appear
in that item's checks with the discovered working directory. This is delivered
through the existing `planner` profile, including refreshed saved proposals;
the provider-boundary test checks its actual outgoing request. For older plans,
item repair recognizes previously executed checks explicitly named in unresolved
criteria. A current failure returns its captured output through worker check
recovery before another reviewer call; stale receipts run through ordinary check
authorization. Passing receipts become candidate-bound `repair_checks` evidence
for independent review. Reviewer snippets never become commands, and neither
the approved plan nor its permissions are rewritten.

Scheduled occurrences reuse `BranchController.prepare` and its ordinary Unattended
worker/reviewer entry points with the operator-approved plan and settings snapshot.
There is no scheduler-authored system prompt, new role or model-callable scheduling
tool. Their new source formats (RSS/Atom and JSON) use the existing `read_url` schema
and URL provenance checks. `test_web` inspects the actual worker request to verify
the updated reader description; the existing runtime profile tests still cover
role, correction, handoff and Resume assembly. Recurrence tests check that a later
default setting cannot replace the captured model choice.

`cheapos/instructions/catalog.py` is the canonical policy registry.
`cheapos/instructions/runtime.py` selects explicit profiles and applies the
existing supersession/conflict resolver to their registered rules. A runtime
profile is a deliberate selection, not the union of every rule for a role.
This matters for a final reviewer, a conversational reply and a recovery
coordinator, which have different tools and output contracts.

| Runtime entry point | Catalog profile or rules |
| --- | --- |
| Worker system, including restarted/handoff requests | `worker`, `interactive`, `unattended`; scoped validation and command policy |
| Repeated reads and compacted worker memory | `recovery.repeated_read_work`, `recovery.repeated_read_research`, `recovery.working_memory` |
| Finish review and worker stages | `recovery.finish_review`, `stage.*` |
| Opening chat / connection greeting | `greeting`, `startup_greeting` |
| Discussion during an existing task | `discussion` |
| Proposal planning, including Resume | `planner` |
| Checkpoint / unattended item review | `reviewer`, `reviewer.item_*` |
| Review correction / decision coaching | `review_reassessment`, `review_decision_coaching` |
| Durable final requirement/integration units | `review_unit`; controller-owned coverage and short delivered evidence handles |
| Legacy final packet, page and synthesis review | `final_review`, current coverage data and `reviewer.original_scope` |
| Evidence reads / citation correction | `reviewer.assessment`, `reviewer.evidence_catalog`, `reviewer.delivered_excerpt`, `reviewer.correct_citation` |
| Review findings / worker repair | `reviewer.defects`, `recovery.disagreement` |
| Recovery coordinator / local chat delegation | `coordinator_recovery`, `coordinator_chat` |
| PR metadata | `publication.worker`, `publication.review`, `publication.final` |

Tool definitions remain with the controller. The tool contract reports the
already-selected tools; it never adds tools, runs checks, expands permissions,
changes routes or approves work. Read-only turns remain read-only. Connection
probes retain their exact small protocol rather than receiving task policies.
The request-local contract is not appended to durable conversation history.

`workflow.ui_completeness` belongs to the worker, interactive, unattended,
reviewer and final-review profiles. Correction, decision coaching and reviewer
handoff retain the primary review policy rather than appending another copy.
Read-only discussion and greetings do not acquire implementation guidance or
tools. Existing saved worker prompts refresh before dispatch; resumed review
requests rebuild the primary profile while retaining evidence and attempts.
Small provider-boundary and recovery tests verify this wiring, tool authority,
non-duplication and final-review receipt reuse. They verify instruction delivery,
not that every model will follow it or that the UI has been visually checked.

## What remains local to producers

Current task IDs, criteria, file inventory, returned evidence, command results,
coverage arguments and exact validation errors remain with the code producing
them. These are facts or schema-specific diagnostics, not a second source of
shared role policy. Tool descriptions stay next to the corresponding schema.
Captured repository guidance and operator messages retain their original text
and authority; this change does not rewrite them into catalog rules.

Unattended guidance remains admissible while the branch is `finalizing`. Chat
uses the existing operator redirect to discard an in-flight response and
reassemble final review with the latest direction. Changed review bindings keep
prior packet history but cannot reuse its approval. The final handoff is
serialized with guidance admission; a message accepted before completion is
reviewed before publication. This does not expand the accepted plan or grant
commands, spending or approval. `ready_for_merge` still requires an explicit
revision for further work. Pure discussion continues through the read-only path.

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
python3 -B -m unittest tests.test_branch_operator tests.test_branch_final_recovery tests.test_branch_review_reuse
python3 -B -m unittest tests.test_planner_inspection_recovery tests.test_branch_review_recovery tests.test_final_review_history
```

The new tests use in-memory providers and existing small fixtures, without Git
workflows, network requests or real-time waits. These checks demonstrate prompt
wiring and preservation of authority/state. They do not establish that a live
model will interpret every instruction correctly, produce a good review or
finish in fewer calls. Live task outcomes still need observation.

## Final synthesis assessment progress

`branch_final._review` offers `record_review_progress` for evidence-contract
synthesis with criterion coverage. The explicit `final_review_progress` profile
shares catalog behavior with item review while auditing its own
`final_review_decision` tool. The controller adds the profile and current checklist
to a fresh provider request after restoring saved evidence; neither becomes part
of completed packet bindings or accumulates across requests.

`test_branch_final_recovery` captures the assembled request, exercises batched
records, rejects incomplete confirmation, then cancels and resumes with another
reviewer through an explicit validated decision. Stale scope, mixed
record/decision batches and changed directions cannot inherit approval. Existing
item-progress, final read-batch and instruction-runtime cases cover the unchanged
paths. These are in-memory tests without model requests, waits or Git fixtures.

New synthesis requests advertise the concise recorded-assessment confirmation
without duplicating the full per-criterion assessment schema. Current check
source mappings travel in the progress checklist. Older complete assessments
remain accepted only through the unchanged evidence validator; request
reservations and authorized limits are not increased.

## Scoped local search

`READ_TOOLS.search` now offers `path`, `glob`, `limit`, `context_lines` and
`cursor` alongside the existing literal `query`. It returns bounded matches,
continuation and explicit clipping/skip metadata; stale source bindings require
a fresh search. The existing `runtime.tool_contract` catalog rule carries the
conditional search-completeness guidance at the provider boundary. No new prompt
entry point, tool authority, review citation or approval path is introduced.

`test_search` inspects the actual `_request_attempt` provider boundary for worker,
Interactive, Unattended, reviewer, read-only work and discussion tools. It executes
returned calls through the real file dispatcher, corrects invalid arguments,
JSON-restores saved state, changes the provider, and completes pagination with
paired replies, preserved checks/grants/attempts and one current contract. A
separate real item-review entry-point test delivers both pages before an explicit
validated decision. Existing runtime/review recovery checks cover phases that
filter search out, including decision coaching and final review; the conditional
prose never grants it back. See [local code search](local-code-search.md) for the
response migration, consumer audit, bounds and filesystem consistency limits.

Search descriptions and repeated contract guidance stay concise because the
conservative reservation counts serialized request bytes, including schemas.
Compacting redundant descriptions restored sample and multi-item execution under
their original 20,000/30,000-token allowances without changing reservation
accounting or removing server-side argument validation. The sample's special
20,000-token override was subsequently removed: new samples capture the saved
reviewer allowance, while existing tasks keep their captured limit. The sample
regression verifies capture and independence from later preference changes;
spending and the shared reservation guard remain unchanged.

## Authorized local browser verification

The existing `workflow.ui_completeness` catalog rule now describes optional browser
verification and retained evidence. Worker/Interactive/Unattended tool sets offer
`browser_preview`; read-only chat filters it out. Dispatch separately enforces the
operator's saved task/workspace and exact preview-configuration grant. Neither tool
arguments nor saved model messages can create consent. Current request assembly still
refreshes the single catalog rule through correction, handoff and Resume.

Item/Interactive/final review offer `read_browser_evidence` and the existing
`inspect_image` reader. Final review units include these in read-only evidence batches;
no reviewer phase receives browser execution authority. Screenshot references resolve
only after current candidate and image digest validation; image assessment retains the
reviewer's normal identity, budget and cancellation path. Text/console observations are
supporting evidence and do not relax code/visual or named-command citation requirements.

`test_runtime_instructions` checks actual provider tool assembly for Interactive,
Unattended and read-only requests without policy accumulation. `test_browser` exercises
consent, startup, changed inputs/configuration, cancellation, restart and the final review
entry through retained evidence, independent image inspection and a separate validated
approval. Existing unit, batch, progress and permission checks preserve review coverage,
integration requirements and model/check authority. Browser lifecycle tests use small
file and in-memory fixtures; real Chromium verification is a separate disposable smoke
check, not a new mandatory heavyweight test.
