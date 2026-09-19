# T04 — Recoverable task deletion and restore backend

**Depends on:** T01. **Size:** M. **Result:** Delete means move a chat to Trash, with its work recoverable.

## Read first

T01 metadata/lifecycle implementation, `cheapos/storage.py`, `cheapos/server.py`, `cheapos/engine.py` entry points, and commit/reconciliation persistence.

## Implementation

1. Add `POST /api/tasks/<id>/trash` and `POST /api/tasks/<id>/restore`, using the existing request-token guard. Deletion is a logical metadata transition; do not move or unlink the source, workspace, snapshot, patch, or history files.
2. On first trash, record `trashed_at` and the prior archived state. Preserve custom title and pin state. Repeating trash must not overwrite the original restore destination or create duplicate history.
3. Default/archived listings exclude trashed tasks. The trash listing exposes title, project, timestamp, saved-change count, and prior state. Full task inspection remains available as read-only.
4. Require an idle runtime and no unresolved commit transaction. Reject trash while starting, running, reviewing, waiting for approval, stopping, or commit-pending. Check the runtime under the engine lock, not only a potentially stale status string.
5. Gate execution mutations for trashed tasks centrally: start/message/steer/check approval/commit/reconcile/rollback must not operate until restore. Reading history/diffs and restoring are allowed. Audit all existing action routes so an API call cannot bypass the UI state.
6. Restore clears trash and returns to the prior active/archived state. It does not restart a model or replay a command. Revoking task-scoped session commands on trash is appropriate; never restore execution permission from history.
7. Use backward-compatible defaults and atomic metadata writes. Unknown IDs and malformed data return useful errors without affecting other tasks.

## Acceptance

- Trash and restore a paused task with edits: source bytes, task patch, events, usage, and commits are identical before/after.
- Trash an archived task; restore keeps it archived. Repeated trash/restore requests are harmless.
- Restart while a task is trashed; it stays in Trash and cannot resume via a direct API call.
- A running task or pending commit cannot be trashed.
- No task directory or source repository is physically removed.

## Validation / limits

Add lifecycle tests plus HTTP rejection coverage. Include a regression for incomplete commit recovery so deletion cannot hide an unresolved transaction. Permanent purge, retention timers, filesystem cleanup, and UI are out of scope. Document that Trash retains disk usage until a later explicit purge feature exists.

## Completion record

Status: Done

- Behavior delivered: Token-protected logical Trash/Restore, prior archive state, saved-change count, idempotent transitions, command-grant revocation, and controller execution guards.
- Acceptance evidence: Saved patch, source, events, usage, and execution record remain identical across Trash/Restore/restart. Live runtimes and pending commits reject deletion. Archived tasks restore to Archived; no files are removed.
- Commands and results: 3 Trash tests, 5 metadata tests, 6 permission tests, and 27 HTTP tests passed. App syntax and diff whitespace checks passed.
- Browser scenarios and results: Backend-only card; UI arrives in T05.
- Remaining limitations: Trash retains disk usage; no purge or retention policy, documented in EXECUTION.md.

Before implementing, read [TASKS.md](../archive/TASKS.md) for the shared contract. Update this record and the matching board row when complete.
