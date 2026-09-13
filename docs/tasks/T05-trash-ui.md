# T05 — Delete, Undo, Trash, and Restore in the sidebar

**Depends on:** T03, T04. **Size:** M. **Result:** users can remove clutter and recover a deleted conversation without a terminal.

## Read first

Sidebar/list/search code from T03, T04 lifecycle responses, and existing dialog/toast helpers in `dist/app.js`.

## Implementation

1. Add Delete to the task overflow menu. Use clear copy: `Move this chat and its saved task work to Trash? Your source project and commits stay unchanged.` Include saved-change count when present. Use `Move to Trash`, not an ambiguous destructive label.
2. For an active task, explicitly offer `Pause & move to Trash`; wait until the worker/check process has actually stopped before calling the trash endpoint. On error, retain the row and explain it.
3. On success, select another visible chat or project home. Show an Undo action tied to the exact trashed task ID, even if the user switches projects. Undo calls Restore; do not reconstruct metadata client-side.
4. Add a Trash view with task title, project, deletion date, saved-work indicator, Inspect, and Restore. Inspection must be read-only with a clear Restore action; disable execution controls until restored.
5. Restore to the recorded prior state. If the task was archived, explain that it returned to Archived. Give a direct navigation action rather than losing it again.
6. Handle refresh, backend rejection, expired local request token, double clicks, and selected-task disappearance without blank screens or auto-inference. Keep task drafts recoverable during navigation in the current session; do not imply draft persistence beyond what the app supports.

## Acceptance

Browser-test delete/undo, reload/restore, archived-to-trash restore, task with unsaved edits, duplicate titles, active pause-and-trash, backend failure, and keyboard use. Use only disposable test tasks. Confirm the source repository is unchanged and a restored patch can still enter the normal review/commit flow.

## Validation / limits

Use T04's API tests plus targeted presentation tests. Do not add permanent deletion or auto-purge. Hide no active work until its stop is confirmed. Do not clear localStorage wholesale or delete directories as a UI shortcut.

## Completion record

Status: Done

- Behavior delivered: Recoverable Delete confirmation with saved-change count; pause-before-trash; ID-bound Undo; Trash listing, inspection, and restore to prior state; read-only archived/trashed views avoid commit-preview requests.
- Acceptance evidence: Backend retains source/patch/history. Failed deletion keeps the dialog and task visible. Restore navigates to Active or Archived based on the server response.
- Commands and results: 3 Trash regressions and 61 JavaScript tests passed; app syntax and diff checks passed; existing 27 HTTP tests passed in T04.
- Browser scenarios and results: Delete/Undo with 2 saved edits; archived-to-Trash; reload and Trash inspection; restore returns to Archived; Pause & move to Trash stops a scripted permission wait; expired token after test-server restart shows inline error and leaves task intact; narrow 390px dialog and Escape checked.
- Remaining limitations: Undo toast lasts 15 seconds; Trash remains available afterward. No permanent deletion or cleanup.

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
