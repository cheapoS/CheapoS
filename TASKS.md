# cheapoS implementation tasks

**North star:** open a project, explain the job, see cheapoS working, authorize routine tests once, approve a finished commit, and keep chatting. For Unattended work, approve a finite proposal, let cheapoS implement/check/review/commit it, then inspect the result and decide whether to merge.

This is the completed first implementation milestone for [the September 13 check-in](CHECK_IN_2026-09-13.md): **sidebar cleanup, clearer task titles, and fewer approval interruptions**, followed by the controller/onboarding improvements below. All 27 cards are Done and record their validation and limitations. Local `main` includes the final integration commit `39903c9`.

**Completed next milestone: [a job on a feature branch](BRANCH_RUNS.md).** All T28–T40 cards are Done, with [validation results](docs/experiments/branch-runs.md) and a [work-mode/trigger guide](docs/unattended-runs.md). Those changes and subsequent live-trial repairs are integrated into `main`. Do not restart T01 or T28.

Original first-milestone baseline: `6f22bf6` (application code `e5bddde`). Notes below that describe that baseline are historical; re-read current code before changing behavior. A dependency means its acceptance checks have passed and its commit is available, not merely that someone started it.

## Start here

**Completed: [T82 — optional coordinator-assisted recovery](docs/tasks/T82-coordinator-assisted-recovery.md).**
Make a configured local coordinator useful after delegation: when a worker gets
stuck, brief the coordinator on saved evidence and let it propose a concrete next
step before asking the operator to invent a correction. Recommend this option in
setup, but keep cheapoS fully usable without it. Start with worker stalls in both
Interactive and Unattended work, including implementation of reviewer feedback.
Keep existing reviewer coaching, permissions, spending policy, and independent
approval intact. Coordinator consultations must be bounded, persisted, accounted,
and visible inside the owning cheapoS reply. The local coordinator stays idle
between interventions and returns to idle as soon as its consultation finishes.

| ID | Task | Depends on | Size | Status |
| --- | --- | --- | --- | --- |
| [T82](docs/tasks/T82-coordinator-assisted-recovery.md) | Give an optional local coordinator saved evidence to help recover stalled workers | Existing progress recovery, T65/T73/T74/T77, T80/T81 | M/L | Complete — [validation](docs/development/coordinator-assisted-recovery.md) |

This card is an implementation handoff, not authorization to start a live trial
or change existing model/spending settings. Complete its ordered increments and
focused validation; do not restart the completed milestones below.

**Completed: T81 — lifetime Usage & savings, plus T79/T80 submission and concurrency.**
The sidebar summary records this installation's reported free/local/included/paid
usage, costs and historical coverage, with explicit local exports. One Interactive
task can now run alongside one Unattended task; local inference and checks retain
one shared slot each. Capacity errors preserve drafts and saved tasks.

| ID | Task | Depends on | Size | Status |
| --- | --- | --- | --- | --- |
| [T81](docs/tasks/T81-lifetime-usage-savings.md) | Durable lifetime usage, free versus paid breakdown, and shareable evidence | Existing T24 metrics and role accounting | M | Complete |
| [T79](docs/tasks/T79-blocked-submission-feedback.md) | Make Send, Enter, and saved-but-not-started feedback agree | Current composer/start flow | S | Complete |
| [T80](docs/tasks/T80-concurrent-interactive-unattended.md) | Interactive and Unattended tasks with isolated ownership | T79; existing workspace, budget, and commit contracts | L | Complete |

See [usage coverage](docs/development/lifetime-usage.md) and
[validation evidence](docs/development/usage-and-concurrency-validation.md).
The earlier live T44 trial remains operator-deferred; this batch used no live
models and did not restart the application or disturb the concurrent stress test.

**Completed: [T78 — planner source excerpts and accurate response diagnostics](docs/tasks/T78-planner-source-excerpts.md).**
The planner can search and page through source files larger than the 64 KB
complete-document limit. Plain-text replies retain their repair context and are
reported accurately rather than being mislabeled as truncated/multiple plans.

| ID | Task | Depends on | Size | Status |
| --- | --- | --- | --- | --- |
| [T78](docs/tasks/T78-planner-source-excerpts.md) | Read large source in bounded excerpts and diagnose missing proposal calls | T65, T73 | S | Complete |

**Completed: [T77 — automatic reviewer reassessment before a routine stall](docs/tasks/T77-reviewer-coaching.md).**
The engine gives an unattended item reviewer one focused, evidence-based nudge
before stopping repeated reads, failed actions, or invalid/no decisions. Chat
shows the recovery attempt; an exhausted attempt retains its specific diagnostic.

| ID | Task | Depends on | Size | Status |
| --- | --- | --- | --- | --- |
| [T77](docs/tasks/T77-reviewer-coaching.md) | Coach a stalled item reviewer automatically within the existing allowance | T60, T73, T74 | S | Complete |

**Completed: [T76 — visible progress from approval to the first worker response](docs/tasks/T76-visible-startup-progress.md).**
Start now applies the returned task immediately, keeps elapsed waiting feedback
visible, and refreshes Chat independently of gateway/sidebar readiness checks.
The accepted first-item wait leads into the actual worker output with Pause
available. No model or backend execution policy changed.

| ID | Task | Depends on | Size | Status |
| --- | --- | --- | --- | --- |
| [T76](docs/tasks/T76-visible-startup-progress.md) | Eliminate the apparent idle gap after approving an unattended plan | T70, T74, T75 | S | Complete |

**Completed: [T75 — one Review & start screen for Unattended work](docs/tasks/T75-single-unattended-approval.md).**
Submit the job directly from the composer, let cheapoS plan visibly in Chat,
then inspect the plan and execution settings together before clicking Start.
Remove the initial mandatory Start unattended work dialog. Use the open project
and saved preferences; keep optional overrides near the composer and request
genuinely missing information inline. Planning uses its already authorized model
and allowance; the final approval authorizes execution, not earlier spending.

| ID | Task | Depends on | Size | Status |
| --- | --- | --- | --- | --- |
| [T75](docs/tasks/T75-single-unattended-approval.md) | Submit directly, plan in Chat, and approve the whole run in one screen | T65, T69, T70, T74 | M | Complete |

T62–T74 below are completed foundations. Extend their saved-plan, immediate-Start,
inline-error, and unified-conversation behavior rather than rebuilding them.

**Completed: T62–T74 — reliable planning, one continuous conversation, and clear failure explanations.**
These completed implementation cards are based on the planner review at
`db774c7` (September 14, 2026) and the operator's follow-up UI requests.
See [validation and browser evidence](docs/development/planner-reliability.md).
The review is a historical reproduction record, not a reason to undo newer fixes. T01–T61 completion records below are
historical, not the next work queue.

### T62–T74 completed implementation queue

The dedicated planner should let an operator choose a stronger planning model
while retaining the existing worker/reviewer loop and authorized spending policy.
After approval, the accepted plan must remain easy to inspect throughout the run.
Clicking Start should immediately return to a visibly starting conversation.

| ID | Task | Depends on | Size | Status |
| --- | --- | --- | --- | --- |
| [T62](docs/tasks/T62-planner-access-binding.md) | Bind planner requests to the authorized gateway and access policy | Current planner implementation | S/M | Complete |
| [T63](docs/tasks/T63-planner-role-selection.md) | Preserve working two-model routes when a planner is configured | T62 | S/M | Complete |
| [T64](docs/tasks/T64-planner-fallback-credentials.md) | Resolve fallback credentials without losing their provider identity | T62 | S | Complete |
| [T65](docs/tasks/T65-planner-configuration.md) | Configure, save, and restore a dedicated planner | T63, T64 | M | Complete |
| [T66](docs/tasks/T66-planner-task-migration.md) | Resume older planning tasks without losing usage or authorization | T64 | S | Complete |
| [T67](docs/tasks/T67-complete-final-plan-checks.md) | Repair plan schema without silently dropping verification coverage | Current plan parser | S | Complete |
| [T68](docs/tasks/T68-planner-usage-visibility.md) | Include planner usage and identity in totals, traces, and the UI | T65, T66 | S/M | Complete |
| [T73](docs/tasks/T73-specific-stop-explanations.md) | Show the actual saved failure and next action directly in Chat | Existing T53/T54 pause contract | M | Completed |
| [T69](docs/tasks/T69-persistent-plan-tab.md) | Keep the approved plan visible and reorder task tabs | Current saved plan contract | M | Complete |
| [T70](docs/tasks/T70-responsive-run-start.md) | Close Start immediately and report startup progress in chat | T69 | M | Complete |
| [T71](docs/tasks/T71-readable-planner-dialog.md) | Widen the planner and make long proposals easier to read | Current planner dialog | S | Complete |
| [T72](docs/tasks/T72-technical-logs-tab.md) | Put Technical logs last and show the newest events first | T69, T73 | S/M | Complete |
| [T74](docs/tasks/T74-unified-orchestration-reply.md) | Keep planning, worker, and reviewer progress inside the owning cheapoS reply | T68, T69, T70, T73; coordinate with T71/T72 | M | Complete |

**Required tab order:** without a plan, **Chat → Changes → Activity → Tests → Technical logs**;
with a plan, **Chat → Changes → Plan & review → Activity → Tests → Technical logs**. The current Checks
label becomes Tests; existing internal view IDs and verification semantics can
stay unchanged. Do not move the operator away from Chat when Start is clicked.
Technical logs show newest entries first, with the latest saved stop/failure
cause easy to inspect. Chat and Activity retain their normal chronological order.
**The main stop banner must already explain the actual recorded issue.** T73
replaces generic “unclassified reason; inspect the diagnostic” copy whenever a
specific safe diagnostic exists. Technical logs provide supporting detail, not
the only way to learn why the task stopped. T73 is listed ahead of the UI cards
because this is an immediate operator blocker; existing task IDs stay stable.
**One visible owner for each operation:** T74 joins the planning announcement,
live status, expandable output, and ready/error result inside the same cheapoS
reply. Remove the separate planning block and detached progress cards. Worker
and reviewer phases follow the same pattern, with actual model identity in
Details and branch metadata in Plan. Do not hide real progress to remove clutter.
For multi-item runs, keep each check, review, and commit attached to its item;
the active reply must identify the current item without borrowing success from
earlier work. The 10:15 screenshots and their item-transition cases are in T74.

Shared completion conditions:

- Preserve explicit Start authorization, reviewer independence from patch
  authors, command consent, exact approved scope, saved work, and accounting.
  A more capable planner does not authorize paid fallback or a larger budget.
- Implement only the selected card. Update its completion record and this board,
  validate the changed paths, and commit only that card's changes before handoff.
- Follow the new-test cost rule below. Use deterministic fixtures and controlled
  promises/events; do not add full agent/Git runs or real sleeps by default.
- For T69–T73, record an isolated browser pass with a saved synthetic proposal,
  a pending Start response, successful start, rejected start, reload, and a task
  without a plan. Verify Technical logs are last, newest-first, and show the
  saved failure detail without changing Chat/Activity order. Reuse one fixture
  across these cards. No personal task or live inference is needed. If
  unavailable, record the exact scenario as pending.
- A stop banner must identify the observed failure, stage, saved-work state, and
  supported next action without requiring Details or another tab. Preserve safe
  diagnostics through persistence and public serialization; never guess a root
  cause or leak raw private provider content just to replace generic wording.
- This task-board update authorizes documentation, not automatic execution of
  all cards or a live trial. A later selected live trial must use measurement
  mode and the operator's existing model/spending policy.

Review evidence: the three reviewed commits are `debbc35`, `0a365d6`, and
`db774c7`; the preceding baseline is `3aa9397`. Local reproductions confirmed
the seven issues in T62–T68. The focused review ran 57 existing tests in 28.790s:
55 passed. The two failures also reproduce at `3aa9397`:
`test_model_pool.FailoverTests.test_unavailable_tool_during_action_recovery_hands_off_without_executing_any_calls`
and `test_branch_planning_http.BranchPlanningHTTPTests.test_missing_runner_retains_complete_plan_and_identifies_executable`.
Do not attribute them to the planner commits or weaken their assertions to obtain
a green report. Record whether they remain when exercising an affected path.

### Previous milestone status

**T49–T60 implemented and validated; browser scenarios remain pending where recorded.** See [review correctness closeout](docs/development/review-correctness.md). T49–T60 turn the halfway assessment and review-loop inspection into bounded implementation and evidence tasks. T49–T55 were planned against `4b6ed68`; T56–T60 against `5a463b4` on `main` (September 14, 2026). Both baselines include the trial's engine fixes. Read current code before assuming a reported issue remains unfixed.

T41–T43 and T45–T48 are recorded below; T44 remains deferred by the operator.
The expanded automatic-routing trial passed, with browser verification pending
where noted. Those earlier cards are not a request to restart completed work.

The [live qualification matrix](docs/trials/matrix/RESULTS.md) establishes that the workflow can complete real work: 30 execution attempts, 18 app-ready outcomes, and no operator interventions after Start in those attempts. Three app-ready results failed independent checks. Models, fixtures, and revisions differed, so these are observations, not a production success-rate estimate. The next iteration should improve correctness and useful completion, not merely raise caps or count more tokens.

Already implemented: stalled-worker handoffs, preserved recovery context, review-schema correction, scoped quota reporting, explicit measurement mode, and faster change-scoped development checks. Extend these mechanisms; do not rebuild them. [Test-performance measurements](docs/development/test-performance.md) show the same 26 commit tests dropping from 120.899 seconds serially to 46.329 seconds in parallel. That is not a complete-suite benchmark.

**New test cost rule:** do not introduce more slow/heavy regression tests by
default. Reuse existing integration coverage and keep new cases small. Before
adding a heavy case, tell the operator its purpose, measured/estimated runtime,
frequency, and why cheaper coverage is insufficient; wait for acceptance of that
extra cost. Report new-test timing at handoff. This applies to every card below.
Live trials are explicitly selected experiments, not additions to everyday tests.

### Upstream maintenance

Use [the upstream compatibility watchlist](docs/upstream-issues.md) to recognize
relevant OmniRoute/OpenRouter failures and track fixes. Review weekly, before
gateway upgrades, and after new local failure signatures. This is a manual
maintenance workflow; no background monitor or automatic routing changes are
configured. Third-party reports remain leads until matched to our own evidence.

| ID | Task | Depends on | Size | Status |
| --- | --- | --- | --- | --- |
| [T61](docs/tasks/T61-upstream-issue-triage.md) | Establish upstream issue triage and a scoped compatibility reference | Current gateway/transport behavior | S | Done — initial triage; repeat maintenance as needed |

T61 includes the repeatable handoff instructions. Subsequent passes update the
watchlist and its review log; any runtime fix gets a separate scoped task.

### T49–T60 implementation record

The operator authorized completion of T49–T60 on September 14. Their completion records below supersede the original ordering notes. This board alone is not authorization to
execute the whole backlog, make live model calls, or change spending policy.
Mark each card Done only against its own acceptance criteria.
The table is ordered by implementation priority, not task number. Existing IDs
stay stable for handoffs; T55 is the final evidence closeout after the new work.

| ID | Task | Depends on | Size | Status |
| --- | --- | --- | --- | --- |
| [T56](docs/tasks/T56-explicit-review-decisions.md) | Require explicit approval; reject missing or contradictory decisions | Current review implementation | S | Done |
| [T57](docs/tasks/T57-canonical-review-findings.md) | Enforce the validated findings throughout repair | T56 | S/M | Done |
| [T49](docs/tasks/T49-complete-repair-coverage.md) | Repair late-item requirements without truncating coverage | T57 | M | Done |
| [T50](docs/tasks/T50-accounted-transport-recovery.md) | Scope transport compatibility and account every retry | Current provider/streaming implementation | M | Done |
| [T51](docs/tasks/T51-predictable-compact-edits.md) | Verify edit sequencing and improve stale-edit recovery | Existing version-bound edits | S/M | Done |
| [T52](docs/tasks/T52-unattended-mode-boundaries.md) | Separate unattended execution from chat while preserving real blockers | Current setup/scheduling | M | Done |
| [T53](docs/tasks/T53-structured-pause-causes.md) | Persist safe, specific pause causes and next actions | Current branch state/errors | M | Done |
| [T58](docs/tasks/T58-focused-review-repairs.md) | Localize repairs and distinguish defects from non-blocking advice | T49, T51, T57 | M | Done |
| [T59](docs/tasks/T59-candidate-bound-review-context.md) | Resolve missing reviewer context against the exact candidate | T56, T57 | M | Done |
| [T60](docs/tasks/T60-review-dispute-progress.md) | Track repeated disputes, progress, and counterevidence | T53, T57, T58, T59 | M | Done |
| [T54](docs/tasks/T54-actionable-pause-ui.md) | Explain pauses and recovery inside the conversation | T53, T60 | M | Done |
| [T55](docs/tasks/T55-halfway-evidence-closeout.md) | Reconcile milestone claims and close focused verification gaps | T49–T54, T56–T60 | S/M | Done |

### What the assessment changes

- T56/T57 address confirmed correctness defects found during review: a missing
  final decision can become APPROVE, and discarded normalized findings can bypass
  the executable-defect write guard. Both reproduced with tiny in-memory fixtures;
  fix them before relying on further unattended qualification.
- The first-12-criteria repair workaround exists in both construction and
  authorization validation. T49 replaces clipping with explicit original
  requirement references while retaining complete final coverage.
- Non-streaming Gemini handling and a stream-error retry are already present.
  T50 makes their scope deliberate and gives every actual attempt its own guards,
  accounting, and visible outcome.
- Shifted-offset protection already exists, including a regression for two edits
  in one response. T51 investigates any remaining path and improves recovery;
  it does not assume the reported corruption still occurs.
- Several unattended prompt/tool gates are fixed. T52 covers the remaining
  lifecycle/dispatch boundaries without removing legitimate blocker reporting.
- T53/T54 address pause diagnosis and operator action separately so the UI has a
  reliable backend contract. T55 qualifies the report's cost/reliability claims
  using retained evidence; the assessment is not an independent billing audit.
- T58 focuses repair scope and preserves counterevidence. Passing checks matter,
  but do not automatically overrule a concrete uncovered defect; optional style
  preferences alone should not block work that satisfies the accepted requirements.
- T59 adds candidate-bound context to final review. T60 tracks repeated disputes
  beyond literal payload equality without claiming every semantic loop is detected.
  T55 also reconciles the pasted table's 46 decisions with the headline's 60 reviews.

Exit for this follow-up: explicit approval, enforced canonical findings, no silent
loss of repair requirements, no unaccounted transport fallback, version-safe edits,
focused repair with retained counterevidence, consistent execution mode, and a
clear next action when paused. Keep new checks small and measured. A new
heavy test still requires advance disclosure and acceptance under AGENTS.md.
The existing exporter deferral and Tasks 6–10 trial proposals remain unchanged.

### T41–T48 implementation record

Earlier planning baseline: `69ab884` on `main`, September 13, 2026. T44 is
deliberately a live cheapoS implementation task; an observing agent must not
silently write that feature itself when it is eventually resumed.

| ID | Task | Depends on | Size | Status |
| --- | --- | --- | --- | --- |
| [T41](docs/tasks/T41-current-validation-docs.md) | Align current validation instructions and exporter trial checks | — | S | Done |
| [T42](docs/tasks/T42-report-acceptance-contract.md) | Prepare independent acceptance evidence for report export | T41 | M | Done |
| [T43](docs/tasks/T43-actionable-review-disagreement.md) | Make review disagreements concrete before changing passing work | T41 | M | Done |
| [T44](docs/tasks/T44-live-report-export.md) | Have cheapoS implement the three-item report exporter | T42, T43 | L | Deferred by operator — two live attempts retained |
| [T45](docs/tasks/T45-report-export-qualification.md) | Verify the real download and record the feature trial outcome | T44 attempted; feature checks require its complete candidate | M | Done — both attempts recorded; feature unqualified |
| [T46](docs/tasks/T46-connection-access-policy.md) | Explicit access, cached health, and scoped failures | T45 findings recorded | M | Done — expanded code; browser verification pending |
| [T47](docs/tasks/T47-outcome-aware-routing.md) | Completed-work selection, served identity, and visible traces | T46 | M | Done — expanded code; browser verification pending |
| [T48](docs/tasks/T48-controlled-routing-trial.md) | Qualify the real gateway path and automatic selection | T47 | M | Done — automatic task independently qualified |

T46–T48 incorporate design lessons from
[free-coding-models](https://github.com/vava-nessa/free-coding-models/tree/536af716263e514723594dd13e755fb06fcdec2d):
versioned health evidence, failure attribution, catalog drift, visible attempt
traces, and pinned checks through the actual router. Each card links the relevant
source. OmniRoute remains the gateway; no additional router/package is required.
Endpoint health remains separate from verified coding outcomes. These additions
do not move the report-export milestone behind a new broad benchmark campaign.

### Current handoff template

```text
T62–T78 are complete. Select the next agreed incomplete card before starting;
do not reimplement these completed fixes.
Read AGENTS.md, CONTRIBUTING.md, TASKS.md, and that card first.
Inspect the current code and verify dependencies; do not restart completed work.
Follow the card's scope, acceptance criteria, and focused validation instructions.
Do not run the full suite solely because you are committing or merging.
Preserve meaningful checks, consent, saved work, and unrelated changes.
Keep new tests fast. Disclose any proposed heavy test and its runtime before
adding it; do not introduce it without the operator accepting that extra cost.

Update the card's completion record and its TASKS.md status. Commit only this
task's changes. Report the commit, actual checks, and remaining limitations.
Do not execute the next card automatically.

For T62–T78, use the reproduction and acceptance contract in the selected card.
Preserve the authorized model and spending policy when adding a stronger planner.
Keep approved plans visible and immutable through the Plan view. Start should
close immediately with honest progress and errors in chat, never fabricated
success or duplicate dispatch. No live model calls are needed for these cards.
Technical logs are the final tab, newest first; never reverse the saved event
array or the chronological conversation to achieve that presentation.
The primary stop banner must surface the recorded problem and next action;
Technical logs are supplementary, not the required route to a useful explanation.
For T74, unify ownership and rendering instead of hiding live output or adding
another status panel. Keep each phase's details and result inside its cheapoS
reply, with honest state and actual planner/worker/reviewer attribution.
For T75, remove the first mandatory setup dialog, not the final execution
authorization. Collect the job from the composer, plan with existing authorized
settings, and present one complete Review & start screen. Edited settings must
produce a current validated proposal; never start with a stale approval token.
For T76, preserve visible startup between server acknowledgement and first model
output as well as before acknowledgement. Diagnose missing state transitions;
do not assume a slow model caused the reported silence. Use controlled promises
and fake clocks to cover a 30-second wait without adding a real-time sleep test.

For historical T49–T60 work, distinguish trial workarounds already in main from remaining gaps.
Do not raise global limits, discard acceptance criteria, enable paid fallback,
or start a live qualification run to make a card pass. Keep browser checks
isolated from personal tasks, and record unavailable scenarios as pending.
Passing tests or an exhausted review allowance cannot substitute for an explicit
valid reviewer decision. Preserve concrete findings and worker counterevidence.

For T44/T48, operate cheapoS as the trial driver. Follow their separate live-run
instructions; do not substitute observer-written code or a scripted model for
a live success. Keep any unsuccessful or assisted attempt in the evidence.
```

Replace both the ID and card path for the selected task. For live runs, explicit
measurement mode follows current AGENTS.md; retain the authorized access and
spending policy, Pause, command consent, usage accounting, and honest failure
reporting. Included account access is not automatically a public free route.

Original T41–T48 milestone target (exporter still deferred): one useful feature implemented through cheapoS, with independent
acceptance evidence, a working operator-facing download, and recorded commit
receipts. A reviewed feature branch remains for the operator's merge decision.
Later routing trials must distinguish a usable endpoint from demonstrated work.

### First-milestone handoff template (historical reference)

Copy this prompt, replace the card path, and send it to the model:

```text
Implement only the task in docs/tasks/T01-task-metadata.md.
Read AGENTS.md, TASKS.md, and that card first. Check its dependencies against
actual code and completed commits. Inspect only the relevant source and tests.
Follow the card's scope, behavior, edge cases, and acceptance criteria.

Existing working code takes precedence over assumptions in the planning notes.
If a named API/file is proposed, implement it; do not assume it already exists.
If a dependency is missing, report the exact missing contract rather than
implementing several other cards or inventing a substitute.

Make small, complete edits. Preserve unrelated changes and existing task data.
Use deterministic local providers and temporary repositories for tests.
Do not use personal API credentials or run a live model task to test the UI.
Use computer use for the described UI checks if available. If it is unavailable,
record that the browser check remains unverified; do not claim it passed.

Run the relevant checks and follow the current repository validation policy.
Do not repeat unchanged passing checks solely because you are changing stages.
Do not weaken tests, limits, permissions, or source-commit safeguards to get green.

When complete, update the task card's completion record and its row in TASKS.md.
Commit only your task changes and report the commit, checks, and any remaining
limitations. Do not start the next card automatically. If running inside cheapoS,
use its reviewer and human Approve & commit flow; never bypass that flow via a
test command. A direct coding agent should follow AGENTS.md for committing.
```

If a card is still too large for a model's output/context limit, stop at a coherent, tested boundary and describe the remaining acceptance items. Do not mark the card Done. Ask the operator to split that card into explicit follow-ups before proceeding; do not silently broaden scope or claim a partial feature is complete.

## Historical first-milestone backlog

The order is recommended, not a request to run all tasks now. Size is relative: **S** = a focused surface, **M** = a few related components, **L** = a carefully bounded integration. Size is not an estimate of model minutes.

| ID | Task | Depends on | Size | Status |
| --- | --- | --- | --- | --- |
| [T01](docs/tasks/T01-task-metadata.md) | Persistent task metadata and lifecycle API foundation | — | M | Done |
| [T02](docs/tasks/T02-task-titles.md) | Useful task titles, editable names, one clear header | T01 | M | Done |
| [T03](docs/tasks/T03-sidebar.md) | Sidebar menus, pin/archive, collapse, and full history | T01, T02 | M | Done |
| [T04](docs/tasks/T04-trash-backend.md) | Recoverable Delete/Restore backend | T01 | M | Done |
| [T05](docs/tasks/T05-trash-ui.md) | Delete, Undo, Trash, and Restore UI | T03, T04 | M | Done |
| [T06](docs/tasks/T06-project-visibility.md) | Remove/reopen a project without deleting its files | T03 | M | Done |
| [T07](docs/tasks/T07-existing-permission-ux.md) | Make existing session approval obvious; diagnose repeats | — | S | Done |
| [T08](docs/tasks/T08-test-profile-matcher.md) | Pure, explicit unittest command-profile matcher | — | M | Done |
| [T09](docs/tasks/T09-project-session-grants.md) | Project-session test grants in the controller | T08 | L | Done |
| [T10](docs/tasks/T10-project-permission-ui.md) | One clear project-test approval and revocation UI | T07, T09 | M | Done |
| [T11](docs/tasks/T11-test-timings.md) | Measure the app's test bottlenecks | — | S | Done |
| [T12](docs/tasks/T12-fast-tests.md) | Fast/focused/full checks and measured fixture improvements | T11 | M | Done |
| [T13](docs/tasks/T13-verification-evidence.md) | Suitable check timeouts and reusable verification evidence | T09, T12 | L | Done |
| [T14](docs/tasks/T14-checkpoint-boundaries.md) | Internal checkpoint boundaries with hard outer limits | T13 | M | Done |
| [T15](docs/tasks/T15-progress-recovery.md) | Bounded recovery with actionable pause explanations | T14 | M | Done |
| [T16](docs/tasks/T16-cooldown-retry.md) | Cancelable waiting for a free route | T15 | M | Done |
| [T17](docs/tasks/T17-work-presets.md) | Simple Free only / working-time controls | T14, T16 | M | Done |
| [T18](docs/tasks/T18-connection-readiness.md) | Structured onboarding readiness and recovery states | — | M | Done |
| [T19](docs/tasks/T19-omniroute-onboarding.md) | Guided OmniRoute setup and return to cheapoS | T18 | M | Done |
| [T20](docs/tasks/T20-local-and-sample-onboarding.md) | Local-only onboarding and an honest sample loop | T19, T10 | M | Done |
| [T21](docs/tasks/T21-project-context.md) | Compact project brief and durable continuation state | — | M | Done |
| [T22](docs/tasks/T22-focused-agent-work.md) | Proactive small edits and stage-appropriate tool/context use | T21 | M | Done |
| [T23](docs/tasks/T23-environment-readiness.md) | Detect missing project tools and explain setup | T13, T21 | M | Done |
| [T24](docs/tasks/T24-completion-metrics.md) | End-to-end task metrics and trustworthy cost display | — | M | Done |
| [T25](docs/tasks/T25-model-selection.md) | Model ranking informed by completed work | T24 | M | Done |
| [T26](docs/tasks/T26-output-filtering.md) | Benchmark optional test-output filtering | T13, T24 | M | Done |
| [T27](docs/tasks/T27-context-compression.md) | Evaluate one optional context-compression layer | T21, T22, T26 | M | Done |

### Final integration gate

Validated after T27 on `work/check-in-tasks`:

- Python full suite: **387 PASS**, 0 failures/errors/skips, **428.861 seconds**.
- JavaScript: **70 PASS**; application syntax check and `git diff --check` pass.
- T26: 24 controlled fixture runs verified; filtering stays off by default.
- T27: eight fixture runs and 28-payload offline replay passed; additional
  context compression is **deferred**, as permitted by the research card.
- Browser scenarios and focused checks are recorded in each task card.
- Temporary UI fixture servers were stopped. That validation run did not merge the branch; local `main` subsequently included `39903c9` before the next milestone was planned.

This historical gate took about seven minutes on this machine. It is not a
current timeout recommendation or a requirement to rerun the suite. Follow
CONTRIBUTING.md for focused iteration and explicitly selected integration checks.

### Milestone exits

- **Daily usability:** T01–T07. A person can identify, rename, find, archive, delete, restore, and reopen work. Existing exact-command session approval is easy to choose.
- **One test authorization, sensible verification:** T08–T13. One explicit project-session grant covers supported unittest variants. Focused tests are fast, and a deliberately selected full suite has time to finish.
- **Less babysitting:** T14–T17. Recoverable problems stay inside a bounded controller workflow. Limits and cooldowns have understandable next actions.
- **Easy first use:** T18–T20. Existing OmniRoute setup connects without manual role/model IDs, and local-only remains available.
- **More capable workers:** T21–T25. Relevant context, small edits, environment readiness, and measured model outcomes reduce waste.
- **Measured optimization:** T26–T27. Filtering/compression is adopted only with preserved correctness and useful end-to-end results.

## Deliberate follow-ups after these milestones

**Deferred: [cheapoS in VS Code chat](docs/development/vscode-integration.md).**
Investigate a thin `@cheapos` chat participant connected to the existing local
engine, inspired by OmniCopilot's model integration. The note records the
architecture, a deterministic Interactive prototype, and unresolved onboarding,
approval, cancellation, and editor-state questions. Implementation is not started
or authorized by this backlog entry; revisit when the operator selects it.

An [optional low-cost model workflow](docs/development/optional-low-cost-workflow.md)
is documented for consideration after T41–T48. It would compare free-only work
with explicitly budgeted paid access using verified completion, cost, elapsed
time, and operator interventions. It is not an active implementation task or
authorization to spend credits; free-only behavior stays unchanged.

The first runner profile is unittest. Pytest/npm profiles, permanent Trash purge,
automatic dependency installation, native installers, and persistent project trust
need separate cards after their underlying contracts are proven. T04/T05 deliver
recoverable deletion now; they do not promise automatic disk cleanup. T19/T23 make
installation/setup guided and actionable without silently installing software.
Do not slip these broader features into a card whose acceptance criteria do not
cover them.

## Shared implementation contract

### Original baseline architecture and known traps

This list describes the pre-T01 baseline, not the completed implementation. For current branch-workflow integration points, use [BRANCH_RUNS.md](BRANCH_RUNS.md) and the source.

- Python 3.9+ standard-library backend, vanilla JavaScript/CSS/HTML in `dist/`. No frontend build step. Do not introduce a framework migration or package manager as part of these cards.
- `dist/app.js` contains sidebar, header, composer, polling, API calls, and UI actions. `dist/guidance.js` exposes pure presentation/conversation helpers used by Node tests.
- `cheapos/engine.py` owns task execution and live `Runtime.task` objects. `Store.get()` returns copies; a worker later saves its own task object. UI metadata edits must not be overwritten by that runtime or overwrite its newer events.
- `cheapos/storage.py` atomically persists task JSON and separately publishes live previews. `cheapos/server.py` has both summary and full-task response paths. Keep their task metadata consistent.
- `/api/bootstrap` and `/api/tasks` currently return task summaries. Existing POST requests use `X-CheapOS-Token`; reuse the same-origin/loopback protections for new endpoints.
- The sidebar currently clips each project's tasks to twelve. Task titles initially copy the first 90 characters of a prompt. `Engine.projects()` combines saved project paths with paths discovered from task history, so removing only a saved path will not hide a project reliably.
- “Allow for this session” already exists for an exact argv and one task workspace. It expires on server restart. Passing check reuse already exists for matching patch/command/generation. Final human commit approval does not rerun tests.
- `run_checks` defaults to 90 seconds; the last full Python development suite took 295.917 seconds. Checkpoint turns default to 12 even when the overall worker-turn allowance is larger.
- `dist/` is served with no-store caching. Reload the UI after frontend changes while preserving the operator's current chat/draft. Backend changes require a controlled server restart; do not interrupt a live user task for a test.
- New static JavaScript files require both an HTML script reference and an explicit addition to `LocalHandler.static_allowed()`. Prefer existing pure helper modules unless a split has a clear purpose.

### Scope and safety that actually affect implementation

1. Work on one card. Do not rewrite the entire engine, implement adjacent cards, or install optimization tools while implementing a sidebar change.
2. Preserve source repositories, saved task copies, raw evidence, existing commits, and unrelated user/worker diffs. Test data belongs in a temporary directory, never the user's `.cheapos/` store.
3. Keep UI metadata separate from execution status. “Archived” and “trashed” are not substitutes for paused/running/reviewing.
4. cheapoS stays the visible orchestrator. Show real worker/check/reviewer activity in its reply. Keep Pause reachable, draft text intact, Details expansion stable, and returning to Chat at the latest response.
5. Automatically running *authorized* tests still needs visible output. Test names do not make arbitrary commands harmless; grant a defined runner scope, not an unrestricted executable prefix.
6. In ordinary manual chats, a model can recommend a commit; only the operator approves the reviewed patch. [The planned branch-run mode](BRANCH_RUNS.md) introduces a separate, explicit up-front authorization for reviewed local feature commits and retains a final human integration decision. It is not a global waiver. A recovered/reconciled code change needs current checks and review. No test command may be repurposed to commit or push.
7. Free-only, local-only, explicit monetary/time caps, and user Pause remain effective. No hidden paid/cloud fallback or unbounded retry. Raw malformed or truncated tool calls never execute.
8. Never put credentials, personal task contents, or arbitrary environment variables in reports, fixtures, metadata, or commits. No new telemetry service.
9. Planned filenames/endpoints in a card are proposed contracts, not existing APIs. Small equivalent designs are acceptable if the same behavior is tested and documented; update dependent cards when a shared contract changes.

### Validation without wasting the whole session

Use the card's focused checks while iterating. Run one relevant UI scenario after the behavior is stable. Follow the current CONTRIBUTING requirements at handoff; T12's focused/full policy is now implemented. Do not repeat unchanged passing checks merely because work moved to review or approval.

Current commands, from the repository root:

```sh
node --check dist/app.js
node --test tests/test_guidance.js tests/test_conversation.js
python3 -B -m unittest discover -s tests -p 'test_permissions.py' -v
python3 -B -m unittest discover -s tests -p 'test_http.py' -v
python3 -B -m unittest discover -s tests -v
```

Change the `-p` filename for the card's relevant test module. New test filenames are proposals until their card creates them. Do not use `python -m unittest tests.test_x` blindly: the existing tests import helpers from the discovery directory.

Use deterministic scripted providers, temporary repositories, and a separate data directory/port for UI fixtures. Never click Pause, Delete, Approve, or Commit on an operator's real task to prove the implementation. For UI cards verify keyboard access, narrow layout, reload persistence, polling updates, and error recovery as relevant. Record any check you could not run.

### Definition of Done and handoff format

A card is Done only when its required behavior and acceptance items pass, relevant existing tests pass, and any manual check is recorded honestly. Update its completion section with:

```text
Status: Done / Blocked / In progress
Behavior delivered:
Acceptance evidence:
Commands and results:
New-test timing and any explicitly accepted heavy-test cost:
Browser scenarios and results:
Remaining limitations:
```

Update the matching Status cell in this file in the same implementation commit. Report the resulting commit hash in the final handoff; do not create another commit just to insert that commit's own hash. A blocked card must name the concrete missing dependency or failed check. Never mark Done merely because a diff exists or a model reviewer said APPROVE.

Run one model against this shared checkout at a time. If the operator deliberately uses multiple agents, give them separate branches/worktrees and integrate dependencies before the next card. Several models editing `dist/app.js` or `engine.py` together will create avoidable conflicts.
