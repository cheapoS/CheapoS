# Storage and task copies

Open **Settings → Storage** to see storage used by this installation and the
cleanup eligibility of each saved task. This is an installation setting, shared
by all its projects and chats; it does not change another installation.

## After a merge

Automatic reclamation is enabled by default. A saved, confirmed local branch
merge or an exact-head GitHub merge receipt makes a task a candidate. An approved
review, a closed but unmerged PR, or a locally synchronized branch alone does not.
GitHub confirmation arrives when cheapoS checks the PR status; offline or unknown
PR states keep their copies.

Before deletion, cheapoS compares file contents and executable modes with the
published revision. It retains copies with unpublished disk or staged edits,
extra files, saved Git stashes, uncertain ownership, or a running task/preview.
Even ignored caches or build output can keep a copy: the app does not guess that
unknown files are disposable. Storage explains the reason. Later edits after a
merged PR can still be recovered with **Continue in a new task**.

Reclaiming removes only the task's isolated working copy and its private Git
metadata. The chat, saved patch/final review packet, reviews, check results and
merge receipt stay available. A completed task's Changes view is read-only;
starting a new preview requires the merged project or a fresh task. Source
projects, their branches, other worktrees, and the GitHub PR are not deleted.
Local Interactive commits keep their open chat workspace; reclamation requires
an actual merged publication or a completed Unattended branch merge.

The app records a cleanup receipt before moving the copy and validates surviving
files if deletion is interrupted. An unexpected change retains the files and is
reported in Storage rather than forcing removal. Old task records can qualify
only when their recorded workspace path matches that task's own storage directory;
new tasks also record directory identity. Symlinked or replaced workspaces are
never followed. There is no sweep based on temporary-folder or branch names.

## Trash retention

The default is **Never**: Trash remains restorable until you choose Empty Trash.
You can instead select 7, 30, 90 or 365 days, counted from when each chat entered
Trash. Saving a period may immediately expire chats already older than it.
Restoring a chat cancels its expiry; trashing it again starts a new period.

Expiry and Empty Trash permanently remove the chat, its task copy and its saved
reviews/checks/attachments. This cannot be undone. Lifetime aggregate usage is
kept separately and is not reset. Busy tasks and uncertain ownership are retained,
with a reason in Storage. Hidden or archived chats are not Trash and do not expire.

## Usage and maintenance

The page shows logical file sizes, not allocated filesystem blocks. Task copies
are a subset of saved-task data. The totals exclude source projects, unrelated
Git worktrees, the global model cache and separately managed preview directories.
Reading the page does not trigger deletion.

Background maintenance runs at startup, when repository operations finish, and
every five minutes while the app is open. **Run cleanup now** applies the saved
policy, including any enabled Trash expiry. Switching off automatic reclamation
retains merged copies; it does not recreate copies already reclaimed. API changes
use the same local-request token protection as other app settings.
