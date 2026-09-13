# CheapOS implementation tasks

**North star:** open a project, explain the job, see CheapOS working, authorize routine tests once, approve a finished commit, and keep chatting.

This is the implementation companion to [the September 13 check-in](CHECK_IN_2026-09-13.md). Start with **sidebar cleanup, clearer task titles, and fewer approval interruptions**. The cards below are specifications for future work; creating these documents did not implement their features.

Baseline inspected: `6f22bf6` (application code `e5bddde`). Re-read current code before editing; earlier cards may already have changed it. All cards initially have status **Todo**. A dependency means its acceptance checks have passed and its commit is available, not merely that someone started it.

## Start here

Give the implementing model **one card at a time**, together with this file. Start with [T01](docs/tasks/T01-task-metadata.md), then [T02](docs/tasks/T02-task-titles.md) and [T03](docs/tasks/T03-sidebar.md). For immediate approval relief, [T07](docs/tasks/T07-existing-permission-ux.md) can be done before the rest of that first milestone, in a separate turn.

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
limitations. Do not start the next card automatically. If running inside CheapOS,
use its reviewer and human Approve & commit flow; never bypass that flow via a
test command. A direct coding agent should follow AGENTS.md for committing.
```

If a card is still too large for a model's output/context limit, stop at a coherent, tested boundary and describe the remaining acceptance items. Do not mark the card Done. Ask the operator to split that card into explicit follow-ups before proceeding; do not silently broaden scope or claim a partial feature is complete.

## Ordered backlog

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
| [T15](docs/tasks/T15-progress-recovery.md) | Bounded recovery with actionable pause explanations | T14 | M | Todo |
| [T16](docs/tasks/T16-cooldown-retry.md) | Cancelable waiting for a free route | T15 | M | Todo |
| [T17](docs/tasks/T17-work-presets.md) | Simple Free only / working-time controls | T14, T16 | M | Todo |
| [T18](docs/tasks/T18-connection-readiness.md) | Structured onboarding readiness and recovery states | — | M | Todo |
| [T19](docs/tasks/T19-omniroute-onboarding.md) | Guided OmniRoute setup and return to CheapOS | T18 | M | Todo |
| [T20](docs/tasks/T20-local-and-sample-onboarding.md) | Local-only onboarding and an honest sample loop | T19, T10 | M | Todo |
| [T21](docs/tasks/T21-project-context.md) | Compact project brief and durable continuation state | — | M | Todo |
| [T22](docs/tasks/T22-focused-agent-work.md) | Proactive small edits and stage-appropriate tool/context use | T21 | M | Todo |
| [T23](docs/tasks/T23-environment-readiness.md) | Detect missing project tools and explain setup | T13, T21 | M | Todo |
| [T24](docs/tasks/T24-completion-metrics.md) | End-to-end task metrics and trustworthy cost display | — | M | Todo |
| [T25](docs/tasks/T25-model-selection.md) | Model ranking informed by completed work | T24 | M | Todo |
| [T26](docs/tasks/T26-output-filtering.md) | Benchmark optional test-output filtering | T13, T24 | M | Todo |
| [T27](docs/tasks/T27-context-compression.md) | Evaluate one optional context-compression layer | T21, T22, T26 | M | Todo |

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

### Current architecture and known traps

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
4. CheapOS stays the visible orchestrator. Show real worker/check/reviewer activity in its reply. Keep Pause reachable, draft text intact, Details expansion stable, and returning to Chat at the latest response.
5. Automatically running *authorized* tests still needs visible output. Test names do not make arbitrary commands harmless; grant a defined runner scope, not an unrestricted executable prefix.
6. A model can recommend a commit; only the operator approves the reviewed patch. A recovered/reconciled code change needs current checks and review. No test command may be repurposed to commit or push.
7. Free-only, local-only, explicit monetary/time caps, and user Pause remain effective. No hidden paid/cloud fallback or unbounded retry. Raw malformed or truncated tool calls never execute.
8. Never put credentials, personal task contents, or arbitrary environment variables in reports, fixtures, metadata, or commits. No new telemetry service.
9. Planned filenames/endpoints in a card are proposed contracts, not existing APIs. Small equivalent designs are acceptable if the same behavior is tested and documented; update dependent cards when a shared contract changes.

### Validation without wasting the whole session

Use the card's focused checks while iterating. Run one relevant UI scenario after the behavior is stable. Follow the current CONTRIBUTING requirements at handoff; **T12 explicitly updates that policy** so every small change no longer implies the same full test run. Until T12 lands, these cards do not silently waive existing required checks.

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
Browser scenarios and results:
Remaining limitations:
```

Update the matching Status cell in this file in the same implementation commit. Report the resulting commit hash in the final handoff; do not create another commit just to insert that commit's own hash. A blocked card must name the concrete missing dependency or failed check. Never mark Done merely because a diff exists or a model reviewer said APPROVE.

Run one model against this shared checkout at a time. If the operator deliberately uses multiple agents, give them separate branches/worktrees and integrate dependencies before the next card. Several models editing `dist/app.js` or `engine.py` together will create avoidable conflicts.
