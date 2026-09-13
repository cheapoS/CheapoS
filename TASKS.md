# cheapoS implementation tasks

**North star:** open a project, explain the job, see cheapoS working, authorize routine tests once, approve a finished commit, and keep chatting. For Unattended work, approve a finite proposal, let cheapoS implement/check/review/commit it, then inspect the result and decide whether to merge.

This is the completed first implementation milestone for [the September 13 check-in](CHECK_IN_2026-09-13.md): **sidebar cleanup, clearer task titles, and fewer approval interruptions**, followed by the controller/onboarding improvements below. All 27 cards are Done and record their validation and limitations. Local `main` includes the final integration commit `39903c9`.

**Completed next milestone: [a job on a feature branch](BRANCH_RUNS.md).** All T28–T40 cards are Done, with [validation results](docs/experiments/branch-runs.md) and a [work-mode/trigger guide](docs/unattended-runs.md). Those changes and subsequent live-trial repairs are integrated into `main`. Do not restart T01 or T28.

Original first-milestone baseline: `6f22bf6` (application code `e5bddde`). Notes below that describe that baseline are historical; re-read current code before changing behavior. A dependency means its acceptance checks have passed and its commit is available, not merely that someone started it.

## Start here

**Next up: trustworthy acceptance, a useful feature delivered by cheapoS, then better automatic model selection. Start with T41.** The two original implementation boards are complete; T41–T48 below are the active backlog. Their planning baseline is `69ab884` on `main` (September 13, 2026). Read current code before assuming anything remains missing.

The [live qualification matrix](docs/trials/matrix/RESULTS.md) establishes that the workflow can complete real work: 30 execution attempts, 18 app-ready outcomes, and no operator interventions after Start in those attempts. Three app-ready results failed independent checks. Models, fixtures, and revisions differed, so these are observations, not a production success-rate estimate. The next iteration should improve correctness and useful completion, not merely raise caps or count more tokens.

Already implemented: stalled-worker handoffs, preserved recovery context, review-schema correction, scoped quota reporting, explicit measurement mode, and faster change-scoped development checks. Extend these mechanisms; do not rebuild them. [Test-performance measurements](docs/development/test-performance.md) show the same 26 commit tests dropping from 120.899 seconds serially to 46.329 seconds in parallel. That is not a complete-suite benchmark.

**New test cost rule:** do not introduce more slow/heavy regression tests by
default. Reuse existing integration coverage and keep new cases small. Before
adding a heavy case, tell the operator its purpose, measured/estimated runtime,
frequency, and why cheaper coverage is insufficient; wait for acceptance of that
extra cost. Report new-test timing at handoff. This applies to every card below.
Live trials are explicitly selected experiments, not additions to everyday tests.

### Current ordered backlog

The cards are instructions for future work, not authorization to execute the entire backlog now. Mark each card Done only against its own acceptance criteria. T44 is deliberately a live cheapoS implementation task; the observing agent must not silently write the feature itself.

| ID | Task | Depends on | Size | Status |
| --- | --- | --- | --- | --- |
| [T41](docs/tasks/T41-current-validation-docs.md) | Align current validation instructions and exporter trial checks | — | S | Not started |
| [T42](docs/tasks/T42-report-acceptance-contract.md) | Prepare independent acceptance evidence for report export | T41 | M | Not started |
| [T43](docs/tasks/T43-actionable-review-disagreement.md) | Make review disagreements concrete before changing passing work | T41 | M | Not started |
| [T44](docs/tasks/T44-live-report-export.md) | Have cheapoS implement the three-item report exporter | T42, T43 | L | Not started |
| [T45](docs/tasks/T45-report-export-qualification.md) | Verify the real download and record the feature trial outcome | T44 attempted; feature checks require its complete candidate | M | Not started |
| [T46](docs/tasks/T46-connection-access-policy.md) | Explicit access, fresh catalog evidence, inexpensive probes, and scoped failure handling | T45 findings recorded | M | Not started |
| [T47](docs/tasks/T47-outcome-aware-routing.md) | Completed-work selection, actual model identity, and visible routing traces | T46 | M | Not started |
| [T48](docs/tasks/T48-controlled-routing-trial.md) | Qualify the real gateway path and automatic selection on one small task | T47 | M | Not started |

T46–T48 incorporate design lessons from
[free-coding-models](https://github.com/vava-nessa/free-coding-models/tree/536af716263e514723594dd13e755fb06fcdec2d):
versioned health evidence, failure attribution, catalog drift, visible attempt
traces, and pinned checks through the actual router. Each card links the relevant
source. OmniRoute remains the gateway; no additional router/package is required.
Endpoint health remains separate from verified coding outcomes. These additions
do not move the report-export milestone behind a new broad benchmark campaign.

### Current handoff template

```text
Implement only T41 from docs/tasks/T41-current-validation-docs.md.
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

For T44/T48, operate cheapoS as the trial driver. Follow their separate live-run
instructions; do not substitute observer-written code or a scripted model for
a live success. Keep any unsuccessful or assisted attempt in the evidence.
```

Replace both the ID and card path for the selected task. For live runs, explicit
measurement mode follows current AGENTS.md; retain the authorized access and
spending policy, Pause, command consent, usage accounting, and honest failure
reporting. Included account access is not automatically a public free route.

Milestone exit: one useful feature implemented through cheapoS, with independent
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
