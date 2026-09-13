# Unattended branch-run proof — 2026-09-13

T28–T40 implement Interactive/Unattended work modes, bounded planning from a prompt, a project document, or both, sequential reviewed feature commits, recoverable execution, and an explicitly approved local fast-forward. See the [user guide](../unattended-runs.md) and [milestone board](../../BRANCH_RUNS.md).

## Method and provenance

`tests/branch_fixture.py` supplies three dependent items: a CSV reader, Markdown renderer, and documented CLI. Distinct scripted worker/reviewer identities return deterministic responses. The planner is scripted too. Git repositories, files, Python subprocesses, assertions, review packets, receipts, HTTP routes, and persistence are real. The initial CSV assertion fails; the worker fixes parsing without weakening the test. The renderer reviewer requests an empty-table test, which is added before approval.

`tests/test_branch_end_to_end.py` independently checks quoted fields, malformed row widths, Markdown escaping, CLI output, the cumulative seven-file diff, exact commit ancestry, an additional documentation correction, stale approval rejection, and local integration. Test execution and model request counts must stay unchanged when merge is approved; there is no extra apply commit. Repeated integration is idempotent.

The three completion browser scenarios used separate temporary projects, storage directories, and loopback servers on ports 53223, 56855, and 59224. A fourth isolated server on port 54761 covered cancellation. They did not use the operator's project/task records or credentials. These fixture servers were stopped and their browser tabs closed afterward. No external inference, paid request, push, or live-model experiment occurred.

## Browser observations and measurements

| Scenario | Completed items / feature commits | Actual check executions | Scripted requests | Accounted tokens, worker + reviewer | Active time | Recorded wall interval |
| --- | --- | --- | --- | --- | --- | --- |
| Prompt only, then final documentation correction and merge | 4 / 4 | 8 | 30 | 760 + 440 | 57.18 s | 233.60 s |
| Document only (`SPEC.md`), then merge | 3 / 3 | 6 | 23 | 640 + 280 | 42.86 s | 120.26 s |
| Prompt + document, edited proposal, pause/guidance/resume, leave on branch | 3 / 3 | 6 | 23 | 640 + 280 | 44.56 s | 161.92 s |

Each browser run included one failed check followed by a successful repair and one reviewer-requested renderer repair. No cached-check reuse event occurred in these changing candidates; unchanged-candidate reuse is verified separately by the item-review test. Final merge itself added zero check executions. Requests include planning. All cost fields are zero from the **synthetic fixture**, even where the UI labels the response's usage as provider-reported; these numbers are not billing observations from a commercial model. Active time is the cumulative run ledger, including planning and execution. The wall interval spans persisted proposal creation through the terminal action, rather than the initial user keystroke. Wall-minus-active intervals (176.42, 77.40, and 117.36 seconds) include inspection, browser operations, and pauses; they are not a precise measurement of human thinking time. Runtime metrics recorded zero waits for intermediate command approval and zero routing cooldowns in the completed document and combined runs.

- **Prompt only:** selected Unattended, entered the request without a document, inspected the full proposal and started once. The source remained clean on its original main until merge. All three outcomes and SHAs appeared; the final diff included both the early reader and later CLI changes. A separately confirmed request for a concrete README example produced a fourth reviewed commit, `4798e737f262f22a72aa516ec75feb647abdcbb0`. Approving local merge made main equal that tip without more tests or requests.
- **Document only:** selected `SPEC.md` with an empty prompt. Switching modes and reloading retained the draft without creating a task or running inference before submission. Planning produced the equivalent three-item plan. Started once, expanded live check/reviewer Details, switched Activity/Chat without losing the disclosure, and reached final review without an intermediate approval. Main became `538d90c070bc43a77b1e382fd3252a7ee4d53a3b`, matching the third feature commit. The UI reported local integration and offered a new chat.
- **Combined and recovery:** an explicit branch-work request in Interactive offered a mode choice. Added `SPEC.md`, edited the first item title, and prepared revision 2 of the same task. Planning usage and both captured inputs remained. A saved/reloaded draft required inspection and Start. Pause retained the first two commits; reload did not resume. Adding guidance did not execute work. Resume completed the third item, `247868f19fcbaaed74a8784d43bbb501348c1e74`. Leave on feature branch retained all seven diff files while disabling integration; main stayed at its baseline `cd24c8ae3c8e5967a10c5d409223f8abd0a245cb`. New chat returned to Interactive.

The uninterrupted runs required **zero intermediate operator approvals**. Initial Start and final merge remained intentional approvals; the requested final correction had a separate confirmation. The combined run deliberately added Pause and Resume. Expanding Details and inspecting files were observation, not requirements to advance execution.

The first prompt-only browser run exposed two rendering defects (a missing task during revision setup and legacy rendering of a review event without a decision). They were fixed and the view reloaded while the backend continued. This was a development rescue, so that initial UI run is not described as flawless. The subsequent independent document run verified the corrected behavior. Additional fixes made saved proposals stay Unattended, kept Pause visible through intermediate approved statuses, shared resume consent with final revision/recheck, and left completed branch previews read-only. Focused JavaScript coverage exercises these regressions.

A separate browser check clicked **Stop planning** while a delayed scripted request was in flight. The UI reported “Stopped after the in-flight model request completed,” retained the prompt, and offered Prepare proposal again. The persisted task was paused without authorization; source refs still contained only main. A preceding request had already completed before the late stop action and remained an unstarted proposal, also without a feature ref. Cancellation does not refund a dispatched request.

At a narrow 760 × 820 viewport the document run had no horizontal document overflow (738-pixel layout width). Sidebar keyboard collapse and top-button restore worked. Existing automated layout coverage also remains part of the JavaScript gate.

## Recovery and evidence coverage

These cases are actual automated Git/process/HTTP/state tests, not claims that every case was clicked through the browser:

| Case | Evidence retained / expected result |
| --- | --- |
| Pause during a real check or route cooldown | Process stops; allowance persists; operator wait is excluded from active time. |
| Restart during worker/check/reviewer phases | No dispatch on startup; transient UI state clears; pending/uncertain usage remains charged. |
| Restart after source ref update | Journal recovery completes that same commit once before the next item; no duplicate commit or adopted external tip. |
| Fresh command grant after restart | Resume requests the matching scope again; durable run authorization alone cannot bypass the expired session grant. This is an expected intervention. |
| Exhausted time, turns, actions, requests, reviewer tokens, or cost | Prospective guard blocks more work; item boundaries, edits, pause, and restart do not refill limits. |
| External feature movement, deletion, ownership/configuration/worktree changes | Block before dispatch or commit while preserving work and evidence. |
| Dirty, moved, or diverged integration target | Saved cumulative diff remains readable; stale merge authorization cannot integrate. |
| Crash after successful local integration but before save | Explicit recovery records the same fast-forward once; operator edits cannot be overwritten. |
| Partial criteria, same-model review, stale checks, missing chunk coverage | Cannot yield a ready receipt or final approval. |
| Read-only refresh and duplicate merge | No model request or check rerun solely for inspection/approval. |

The coverage lives in `test_branch_budget`, `test_branch_recovery`, `test_branch_commits`, `test_branch_workspace`, `test_branch_evidence`, `test_branch_review`, `test_branch_final`, `test_branch_completion`, `test_branch_merge`, and the HTTP/planner modules. Expected safety pauses are separate from avoidable repeated routine-check prompts.

## Regression gate

- `node --check dist/app.js` and `node --check dist/branch_ui.js`: passed.
- `node --test tests/test_*.js`: 88 passed, 0 failed/cancelled/skipped, 0.104 seconds.
- `python3 -B scripts/dev_tests.py --suite full --timings --json /tmp/cheapos-branch-full-release.json`: **514 passed**, 0 failures/errors/skips, **1,107.087 seconds (18 min 27 s)**. This includes 119 branch-run tests and seven recovery test methods exercising multiple interruption stages.
- Environment: Python 3.9.6, macOS/Darwin arm64; standard-library fixtures, real local Git and subprocesses.
- `git diff --check` and local documentation-link validation: passed.

The final full-run end-to-end proof measured 96.86 seconds wall time and 66.34 seconds active time, four commits, eight actual checks (one failure), one reviewer-requested repair, 29 scripted requests, 720 worker + 440 reviewer tokens, zero cost, and zero intermediate operator approvals. Structured preparation omits the browser planner request. The three completed items and fourth correction all retained their original receipts and ancestry.

The slowest full-gate cases were the end-to-end job (97.017 s including setup/cleanup), sequential three-item execution (55.794 s), existing controller benchmarks (28.460 s), integration-save recovery (24.817 s), and all durable commit-failure boundaries (23.680 s). These retain real repository/process behavior. Active time increased after the additional staged-content validation; these development measurements are not a controlled speed comparison.

During development, an earlier full run found four final-review test-fixture errors after event emission was added, then stalled in an older review fixture that injected Interactive permissions. The final-review fixture now supplies the event callback and asserts the decision; its six focused tests passed in 80.425 seconds. The item-review fixture now obtains and verifies a real branch-scoped grant; both focused tests passed in 5.319 seconds. The stalled run was stopped, and the entire suite restarted with the corrected fixtures. No production permission check was relaxed.

A final audit also found that a subprocess could stage a newly introduced excluded file in the private index. Branch candidate extraction and commit recovery now validate staged paths, file modes, and blob sizes without discarding that index; source-tree validation provides another check before ref movement. Real Git regressions cover excluded names, symlinks, gitlinks, oversized blobs, and valid executable/deleted files. A concurrent-planning regression also exposed a gap between checking for an active task and registering the planner. Registration now repeats the check atomically before reserving usage or requesting a model; a losing draft pauses with an actionable message and zero usage. The race test passed in 0.225 seconds and all five planning HTTP tests passed in 18.332 seconds. The replacement full run was restarted after these production fixes so the final gate would load the same implementation throughout.

The first end-to-end focused proof took 109.87 seconds, with 47.78 seconds of active run time, four commits, eight checks, and 29 scripted requests (structured preparation omits the planner request). Profiling showed that fetching unusually tiny diff pages added repeated Git validation overhead. The test now fetches 1,000-character pages while still asserting that every page reconstructs the complete seven-file diff; production validation and recovery coverage were retained.

## Scope and remaining limits

This proves controller behavior with deterministic providers, not real-model task quality, savings, or reliability. The subsequent trial in BRANCH_RUNS.md requires selecting a useful bounded app improvement, routes, and limits with the operator; this milestone did not pre-implement that trial.

Plans are finite (at most 50 items), review evidence is bounded, and missing/oversized coverage blocks readiness. There are at most three bounded repair amendments, covering at most twelve distinct original criteria. Model identity must be independent. Existing uncommitted source edits are excluded. Task storage must be outside the edited repository, including when cheapoS edits itself. Integration is local fast-forward only: a dirty/diverged target or one held by another worktree requires operator resolution. Publishing, scheduling, broader authorization changes, and automatic conflict resolution remain separate future work. Automatic feature commits are not human acceptance.
