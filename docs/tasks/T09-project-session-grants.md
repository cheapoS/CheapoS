# T09 — Project-session test grants in the controller

**Depends on:** T08. **Size:** L. **Result:** one explicit unittest-profile grant covers valid test variants in authorized copies of the same project for the current server session.

## Read first

T08's profile schema/matcher, `Engine.approve_check`, `checks`, pending approval construction, `session_permissions`, `reconcile_project`, task creation, startup/shutdown, and `tests/test_permissions.py`.

## Implementation

1. Add an in-memory project-session grant registry owned by Engine. Bind a grant to a canonical project identity, the approved executable/runner/profile, and the applicable runner configuration fingerprint. Do not persist grants or revive them from permission events.
2. Scope workspaces through cheapoS's registered source/snapshot relationship, not a path prefix provided by the model. A fresh task copy of the same known project can match; an arbitrary directory or replacement repository cannot. Document how source identity changes are detected.
3. Extend pending approvals with a server-generated eligible profile proposal when T08 recognizes the command. Keep exact-command proposals available for everything else. The model cannot mint a profile or grant ID.
4. Extend the approval API with an explicit scope value (once, task_exact, project_tests_session) while preserving legacy remember requests. Revalidate approval ID, command, project/workspace, and profile/configuration identity at approval time. Reject stale or incompatible grants.
5. Route checks through one authorization decision: exact grant, matching project profile, legacy supported permission, or ask. Record the actual command and authorization scope used. Permission does not imply the test passed or is reusable.
6. Add read/revoke support for the selected project's grants. Revoke affects future executions only. Restart expires every project-session grant.
7. Reconciliation may reuse a grant only when the source project and approved runner/configuration scope still match. Ordinary edits to tests are expected within the approved scope; do not invalidate the grant on every changed test file. Changes to the executable or applicable script/configuration boundary require a fresh decision.
8. Preserve once-only approval, existing task-exact grants, user Pause, deadlines, and human commit approval. No global auto-approve switch.

## Acceptance

Grant once and run two approved test selectors; use a follow-up and another cheapoS-created copy of that project without a second prompt. Another project, outside workspace, changed runner/configuration, stale approval, or restart requires approval. Revocation and reconciliation behave as specified. An unchanged passing check is still reused rather than rerun merely to exercise the grant.

## Validation / limits

Expand permission, HTTP, reconciliation, and review-workflow regressions using a scripted provider. Include concurrent revoke/approval and source identity changes. Public error messages should explain scope without exposing secrets. T10 owns UI; this card must leave old clients usable. Do not add pytest/npm, persistent trust, or command execution through a shell.

## Completion record

Status: Done

- Behavior delivered: Ephemeral project grant registry; server-generated profiles; explicit once/task_exact/project_tests_session scopes; read/revoke API; legacy remember compatibility; current profile revalidation and recorded execution scope.
- Acceptance evidence: Six project-grant regressions cover selector/follow-up/new-copy reuse, stale profiles, configuration changes, source/copy replacement, revocation/restart, and reconciliation. Source and .git device/inode identity (plus worktree git-file content) detect repository replacement; only registered task/reconciliation destinations qualify. Executable stat and runner/startup configuration hashes form the fingerprint; ordinary test content does not. Revocation invalidates older proposals.
- Commands and results: 6 project-grant tests, 7 legacy permission tests, 29 HTTP tests, 2 review workflow tests, and 61 JavaScript tests passed; syntax/diff checks passed.
- Browser scenarios and results: UI remains compatible with legacy clients; broader scope UI is T10.
- Remaining limitations: Grants are server-session only, unittest only, and not a sandbox. External file changes after authorization remain subject to the normal local execution model.

Before implementing, read [TASKS.md](../archive/TASKS.md) for the shared contract. Update this record and the matching board row when complete.
