# T34 — Pause, restart, and external branch changes

**Depends on:** T33. **Size:** M. **Result:** an interrupted run resumes from saved facts rather than repeating work, renewing limits, or silently following another branch.

Read [BRANCH_RUNS.md](../archive/BRANCH_RUNS.md) and AGENTS.md first. This card hardens the scheduler; it does not add automatic reconciliation or branch adoption.

## Read first

`Engine.stop/shutdown/start`, `Store.__init__`, process cancellation in Workspace, route waiting, ephemeral command grants, T32's journal, and T33's cumulative ledger.

## Implementation

1. Pause stops further dispatch and cancels active model/check work through existing mechanisms. Keep a clear distinction between requested pause, cancellation in progress, and paused. Commit operations have a short noninterruptible consistency boundary: finish/reconcile their journal safely, then stop before the next item. Do not claim instant cancellation of an already completed commit.
2. On server startup, load run state without dispatching models, checks, commits, or merge actions. Mark interrupted activity appropriately and clear ephemeral streams/pending command proposals. Preserve ownership mapping, authoritative commit receipts, accepted plan, consumed budget, and final evidence.
3. Explicit Resume first reconciles pending T32 operations, revalidates project/workspace identity and expected feature tip, then determines the first genuinely unfinished stage. Do not ask the worker to implement a committed item again. Rebuild bounded context from the accepted plan and durable outcomes.
4. Keep run authorization distinct from expired command grants. Resume may retain the unchanged accepted branch contract, but must request a new eligible test grant if the server restarted. Explain this once with the covered scope; never reconstruct grants from historical permission events.
5. Detect feature ref deletion, external advancement/rewind, ownership mismatch, source replacement, and the feature being checked out elsewhere. Pause with expected versus observed state and actionable text. Do not force-reset, recreate, adopt, or overwrite the ref. Leave saved work inspectable; automatic branch-drift reconciliation is a later feature.
6. Target-branch advancement is different from feature-ref interference. Continue isolated implementation when authority/base still match, record target drift, and invalidate any final target-bound preview. T37/T39 decide final integration readiness. Do not interrupt every item just because unrelated work lands on the target.
7. Archive/trash while running must pause through the same path and retain branch/workspace/receipts. Restore is not Resume. Revoking automatic continuation stops future dispatch; no automatic deletion of commits or source branches. Keep existing history APIs compatible.

## Acceptance and validation

Restart during a worker request, tests, review, and after a source commit but before its final save. Each resume uses the correct stage; receipts/events are not duplicated; uncertain usage stays charged; outer time/turn limits remain consumed.

Pause during cooldown and tests; verify subprocess cancellation and no next-item dispatch. Test another linked worktree checking out the feature, source identity replacement, target movement, and feature movement as distinct outcomes. Refreshing the UI or starting the server alone must perform no execution. Use deterministic time/failure injection where possible, without removing real process/Git tests.

## Completion record

Status: Done

Behavior delivered: Resume reconciles journaled commits before new work, revalidates ownership and feature tip, and renews expired test scope separately from durable run authority. Pause/restart keeps cumulative accounting and artifacts.

Acceptance evidence: Seven recovery tests passed: real process and cooldown cancellation, blocked reviewer restart, staged worker/check/review recovery, scope renewal, feature/worktree interference, target drift, and source-CAS crash recovery.

Commands and results: test_branch_recovery.py: 7 passed in focused runs (30.633s + 16.638s).

Browser scenarios and results: Combined-input browser run paused with two commits, survived reload without execution, accepted guidance, and resumed to the third commit.

Remaining limitations: External feature changes are never adopted or reset automatically.
