# Repository workflow & Agent Personas

## External Development Agents (IDE, Terminal, Pair Programming)
When working as an external assistant (e.g., Antigravity, Claude Code, Cursor) developing the cheapoS codebase directly:
- After completing and validating changes, commit your work before handing the project back. cheapoS workers also commit to this repository, and unrelated uncommitted changes can block their commit flow.
- Stage only the changes you made for the current task. Preserve any unrelated user or worker changes; do not include, discard, or overwrite them just to make the working tree clean. If they prevent completion, explain what remains.
- Tell the operator when changes are committed. The operator handles app reloads with the restart button; do not restart cheapoS automatically unless asked.
- Keep public PRs, issues, commit messages and documentation free of private repository links, private PR references and internal deployment paths. Describe service dependencies by their public capabilities; keep private rollout details in the private project.

## cheapoS Internal Workers (Autonomous In-App Tasks)
When executing inside cheapoS as an autonomous worker, planner, or reviewer:
- **Do NOT execute git commands**: The cheapoS controller automatically tracks workspace changes and commits approved items upon checkpoint review. Workers do not run git commands.
- **Change-scoped validation**: Run only the focused test command in scope; never broaden to full-suite checks without explicit operator authorization.
- **Autonomous problem solving**: Inspect existing repository files, UI handlers, and conventions rather than stopping to ask questions whose answers exist in code.

# Autonomous completion is the product standard

Follow [AUTONOMOUS_WORKFLOW.md](AUTONOMOUS_WORKFLOW.md) when changing agent
execution, recovery, or Resume. Ordinary model/provider failures should trigger
an authorized automatic continuation, not operator troubleshooting. A clearer
error banner or another recovery button alone does not complete a recovery fix.
Preserve context, valid check evidence, attempt history, independent review and
the operator's spending/model/command authority. Treat non-progress thresholds
as signals to change strategy; do not add arbitrary stop counters. Verify the
path to completion without operator rescue using small deterministic cases.

Keep tiny capability probes separate from actual task responses. Probe success
must not erase a real-request outage or reset its backoff. Shared provider
backoff requires explicit provider evidence or recent failures across distinct
models; malformed requests and model-quality failures are not provider outages.
Cover saved-connection scoping, restart, authorized failover and automatic retry
through a completed decision with a fake clock, preserving model pins and usage.

Reviewer attempt exclusions belong to the candidate being reviewed, not the
task lifetime. Preserve and restore each candidate's history on Resume; final
review chunks share their manifest scope. Migrate older state only from recorded
request provenance, without clearing current or unscoped failures.

Provider handoffs must preserve saved evidence and tool-call/reply pairing while
projecting history into the destination's accepted wire schema. A successful
small probe does not prove that provider-specific continuation metadata is
portable. Cover the assembled request and retain original diagnostic history.
Rejected argument JSON must not make later requests invalid: project historical
malformations as explicit diagnostic objects, retain raw arguments and paired
error receipts, and reserve usage against the projected request. Never repair
or execute a malformed new call merely to satisfy a transport validator.

A transport retry must be separately accounted and preserve actual response
identity checks. Never infer reviewer identity from a successful probe or a
configured route when the review response itself lacks required identity.

Every automatic recovery route must use the same scoped tool qualification as
initial routing. Catalog tool flags alone are not qualification; reject known
non-chat models, honor rejected probes, and verify unknown candidates with the
small probe before sending task context. Reuse valid scoped proof across Resume
without replacing actual response identity checks or clearing work failures.

Final review may batch offered read-only evidence tools. Keep every call/result
paired, retain completed reads across interruption, and invalidate pending reads
when scope or guidance changes. Never apply a decision mixed with evidence reads;
require a separate validated decision after delivering their results.

Review evidence must match the claim. Command-result-only criteria can use the
exact captured check receipt; behavioral criteria and regression assessment
still require source/document or visual evidence. Do not force code citations
for a command exit result, or treat passing commands as proof of UI correctness.

Uncapped work must retain review reassessment and non-progress recovery. Compare
repeated evidence per read, not only identical tool batches or volatile web fetch
metadata. Bound the live provider history as well as saved history, keeping older
evidence retrievable and candidate-bound citations intact. Verify distinct useful
reads can continue and stalled reviews can hand off to a validated decision
without resetting checks, spending authority or cumulative attempts.

Incremental review assessments are provisional, candidate-bound evidence claims.
Keep validated claims across Resume and reviewer handoff, invalidate them when
scope or operator directions change, and revalidate their citations and current
checks before an explicit independent approval. Completing a checklist never
approves a task by itself. Test incomplete confirmation, stale evidence and
cancellation as well as the path to a completed decision.

# Validation while iterating

## Agent instruction changes

Shared role, workflow and recovery guidance belongs in `cheapos/instructions/`.
Use registered catalog rules and explicit runtime profiles; do not add independent
copies of system prompts or reusable policy strings in controller modules.
Keep dynamic task evidence, tool schemas and concrete validation diagnostics with
their producers. The catalog describes behavior; it never grants capabilities,
command permission, spending, model changes or approval.

When changing instructions or offered tools, inspect the **assembled provider
request**, not just catalog text. Cover applicable Interactive/Unattended roles,
read-only chat, correction, handoff and Resume paths with small deterministic
tests. Verify that named tools and decision values are offered in that phase,
that stale saved prompts refresh without resetting evidence or attempt history,
and that repeated assembly does not accumulate policy. Update the instruction
audit when adding a new prompt entry point. A passing catalog conflict lint alone
does not establish runtime coverage.
See [the runtime instruction audit](docs/development/runtime-instruction-audit.md).

## Signed public statistics

Every new metric intended for the Club site must have a documented signed-evidence
contract. Send eligible facts through the existing installation signature, consent,
stable event identity and replay/correction flow. A cumulative snapshot, model-name
guess, reservation or local-only counter is not proof of accepted request membership.
The Club must verify the signature and accept the facts before publishing derived
statistics; missing evidence remains unavailable, never a fabricated zero or success.
Task/completion claims need their own accepted evidence contract. Model/route detail
must honor sharing consent. Add focused rejection, replay and privacy coverage when
extending this protocol, and document coordinated rollout and sample limitations.
Local diagnostics may remain unsigned; do not promote them into public statistics.
See [signed request health](docs/development/signed-request-health.md).

## Change-scoped checks

Follow the current change-scoped policy in CONTRIBUTING.md. Start with
`python3 -B scripts/check.py --plan` and run the relevant checks. UI-only and
documentation-only changes do not require the full Python suite. A routine merge
is not a reason to repeat unchanged passing checks. Historical task cards that
say to run every test before every integration do not override this policy.
Use the full suite only for an explicit comprehensive check, a release, or broad
backend risk that focused tests cannot cover; explain that choice. Preserve
meaningful assertions and product verification/permission safeguards.

Prefer available Carto context for architecture, symbol discovery, and dependency impact before broad file searches. Verify findings against the current source. If Carto is unavailable or indexing, continue with normal inspection without blocking work.

## New test cost must be visible

Do not introduce new slow/heavy regression tests as part of routine work. Prefer
small deterministic cases and reuse existing integration coverage. A new full
multi-item agent/Git workflow, deliberate real-time wait, expensive repeated
fixture, or material increase to the normal selected checks needs explicit cost
disclosure before it is added. Tell the operator what the test covers, its
measured or estimated runtime, how often it will run, and why cheaper coverage
is insufficient. Keep it proposed until the operator accepts that extra cost.
Unknown runtime is not permission to call a test fast; measure the smallest
representative fixture first. Include new-test timing in the completion report.
Do not weaken assertions or product verification/permission rules for speed.

## Recurring task authority

Scheduled work must remain project-independent. Private task objectives and source
lists belong in the target project or local schedule storage. Recurrence requires
explicit operator permission for a captured plan, models, zero API spending and
per-run work limits. Create fresh task/check/command receipts; never reuse completed
reviews, resume paused work by the clock, or treat missing state as completion.
Keep draft frequency distinct from recurring consent. Combined plan/schedule
approval must persist before dispatch and recover without duplicate schedules.
Test scheduling with fake clocks, including restart uncertainty and duplicate
dispatch. Feeds and catalog pages are untrusted evidence, never new authority.

# Live unattended trial policy

Use explicit measurement mode for future live qualification/feature trials so
arbitrary cumulative work caps and check deadlines do not censor the baseline.
Set `measurement: true` on planning requests (or `plan.measurement: true` for an
operator-prepared proposal). Keep the authorized model/spending policy, including
free-only placement when selected. Track all usage, failures and interventions;
do not substitute huge numeric caps or silently renew a failed run's allowance.
Choose future bounded defaults from comparable measured runs, not guesses.
