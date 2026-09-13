# T09 — Project-session test grants in the controller

**Depends on:** T08. **Size:** L. **Result:** one explicit unittest-profile grant covers valid test variants in authorized copies of the same project for the current server session.

## Read first

T08's profile schema/matcher, `Engine.approve_check`, `checks`, pending approval construction, `session_permissions`, `reconcile_project`, task creation, startup/shutdown, and `tests/test_permissions.py`.

## Implementation

1. Add an in-memory project-session grant registry owned by Engine. Bind a grant to a canonical project identity, the approved executable/runner/profile, and the applicable runner configuration fingerprint. Do not persist grants or revive them from permission events.
2. Scope workspaces through CheapOS's registered source/snapshot relationship, not a path prefix provided by the model. A fresh task copy of the same known project can match; an arbitrary directory or replacement repository cannot. Document how source identity changes are detected.
3. Extend pending approvals with a server-generated eligible profile proposal when T08 recognizes the command. Keep exact-command proposals available for everything else. The model cannot mint a profile or grant ID.
4. Extend the approval API with an explicit scope value (once, task_exact, project_tests_session) while preserving legacy remember requests. Revalidate approval ID, command, project/workspace, and profile/configuration identity at approval time. Reject stale or incompatible grants.
5. Route checks through one authorization decision: exact grant, matching project profile, legacy supported permission, or ask. Record the actual command and authorization scope used. Permission does not imply the test passed or is reusable.
6. Add read/revoke support for the selected project's grants. Revoke affects future executions only. Restart expires every project-session grant.
7. Reconciliation may reuse a grant only when the source project and approved runner/configuration scope still match. Ordinary edits to tests are expected within the approved scope; do not invalidate the grant on every changed test file. Changes to the executable or applicable script/configuration boundary require a fresh decision.
8. Preserve once-only approval, existing task-exact grants, user Pause, deadlines, and human commit approval. No global auto-approve switch.

## Acceptance

Grant once and run two approved test selectors; use a follow-up and another CheapOS-created copy of that project without a second prompt. Another project, outside workspace, changed runner/configuration, stale approval, or restart requires approval. Revocation and reconciliation behave as specified. An unchanged passing check is still reused rather than rerun merely to exercise the grant.

## Validation / limits

Expand permission, HTTP, reconciliation, and review-workflow regressions using a scripted provider. Include concurrent revoke/approval and source identity changes. Public error messages should explain scope without exposing secrets. T10 owns UI; this card must leave old clients usable. Do not add pytest/npm, persistent trust, or command execution through a shell.

## Completion record

Status: Todo

- Behavior delivered: —
- Acceptance evidence: —
- Commands and results: —
- Browser scenarios and results: —
- Remaining limitations: —

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
