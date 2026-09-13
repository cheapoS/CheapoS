# T40 — Three-task end-to-end proof and documentation

**Depends on:** T28–T39. **Size:** M. **Result:** the milestone is demonstrated through actual UI, Git, tests, reviewer feedback, recovery, and final approval, with limitations reported honestly.

Read [BRANCH_RUNS.md](../../BRANCH_RUNS.md), AGENTS.md, and CONTRIBUTING.md first. This is a verification/release card, not permission for a broad engine rewrite or unbounded live-model experiment.

## Read first

Existing deterministic provider/HTTP fixtures, `cheapos/benchmark.py`, metrics exports, browser fixture conventions, test performance report, and every preceding card's completion record. Confirm their dependencies are actually present.

## Implementation and scenarios

1. Add a reusable temporary fixture with a committed baseline, source target branch, independent scripted planner/worker/reviewer responses, and three dependent items: implement a small CSV reader with tests, add Markdown rendering with tests, then add CLI wiring and documentation. Use standard-library unittest and a final suite covering all three. Pin expected behavior and test it independently of worker prose.
2. Script one real initial assertion failure followed by a valid repair and one reviewer REQUEST_CHANGES followed by a valid revision. Each item ends with one meaningful reviewed commit. The failure should exercise recovery without teaching the worker to weaken tests; the final checks must actually execute and inspect behavior.
3. Drive the complete browser flow independently for prompt-only input and for a selected project document (no pasted duplicate or required checkboxes); both must yield equivalent validated three-item plans and the same authorization/execution behavior. Cover the combined prompt/document path and the trigger/non-trigger contract from BRANCH_RUNS.md. For each complete run: select **Work mode → Unattended**, select the disposable project, request the plan, inspect/start once with test scope, expand live Details, observe all three items/SHAs, and reach the final cumulative review with **zero intermediate operator clicks** in the uninterrupted run. Assert earlier files and later edits are both visible in the final diff. Real Git objects/files and subprocess results are required, not only mocked JSON or screenshots.
4. Request an in-scope correction at final review, observe a fourth reviewed commit and renewed final readiness, then approve one local fast-forward. Confirm target tree, ancestry, exact commit receipts, no extra apply commit, correct local-merge message, and the next-work prompt. No tests rerun solely because the final approval was clicked.
5. Run separate recovery scenarios for restart mid-review and after commit ref update, Pause during tests/cooldown, exhausted cumulative time/usage, external feature-tip movement, target advancement/divergence, dirty source edits, and stale final approval. Restart must require expired command scope again; report that expected intervention separately from avoidable prompts. No scenario may discard work or execute on server launch.
6. Add concise user documentation with a prompt-only walkthrough, a project-document walkthrough, and a trigger table matching BRANCH_RUNS.md (proposal, Start, Pause/Resume, revision, final merge, and non-triggers). Explain **Interactive** versus **Unattended**, the default and mode-switch behavior, separation from model placement/budget presets, committed-base behavior, independent-review requirement, session grants/restart, limits, final actions, and first-version merge restrictions. Update README/onboarding links as appropriate without burying the quick start in implementation details. Document the separate future options for publishing, scheduling, and conflict resolution.
7. Record measured counts/timing in a local experiment report, for example `docs/experiments/branch-runs.md`: completed items, commits, check executions/reuse, review revisions, interventions and reasons, total/active/operator-wait time, recovery counts, and synthetic versus provider-reported usage. Automatic commit is not human acceptance. Do not claim model-quality/cost savings from scripted fixtures.
8. Run the required complete Python and JavaScript integration gate once after the implementation is stable; report test counts, failures/skips, elapsed time, and environment. Preserve broad Git/process/restart coverage. Profile newly slow cases before changing fixtures; do not weaken coverage to meet a time target. Update BRANCH_RUNS.md's board and final completion notes.

## Acceptance

The happy path and final revision/merge are independently verified through computer use with a temporary project and separate data directory/port. Recovery cases pass and retain evidence. Manual chat/commit, sidebar/history, test permissions, local setup, free-route behavior, and panel resizing still pass relevant regression checks.

Never click actions on the operator's real task as a test. Stop disposable fixture servers afterward. If computer use is unavailable, explicitly leave the browser acceptance unverified and do not declare this milestone complete.

A live free-model trial is a subsequent operator-authorized test with selected routes and a known limit. Keep its outcome separate from this deterministic implementation proof; do not spend personal API credits merely to finish this card.

The next check-in after this card is to select a real cheapoS feature for the app to implement itself using the new workflow. Follow the process in BRANCH_RUNS.md: choose the feature after reviewing this milestone, write its bounded spec, then run it through the actual UI. Do not pre-implement that feature here or substitute external-agent edits for cheapoS's work.

## Completion record

Status: Todo

Behavior delivered:

Acceptance evidence:

Commands and results:

Browser scenarios and results:

Remaining limitations:
