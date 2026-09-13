# T10 — One clear project-test approval and revocation UI

**Depends on:** T07, T09. **Size:** M. **Result:** supported test runs ask once for a useful scope, and the operator can inspect/revoke it easily.

## Read first

T09 pending approval and permission APIs, T07 composer control, Chat/Activity approval markup, and existing Details/session UI.

## Implementation

1. When the server offers a recognized unittest profile, show primary `Allow project tests for this session`, plus Run once and Decline. For unrecognized commands retain exact-command session approval from T07; never imply broader permission exists.
2. Show a concise scope explanation with expandable details: project, runner, test roots/allowed variants, and expiry. Say that these tests execute project code, including subsequent test edits. Avoid a wall of repeated warnings.
3. Submit the explicit scope and current approval ID. Disable duplicate clicks while pending. Handle stale proposal/revocation failures by refreshing the current request; do not automatically choose a different scope.
4. The composer control reads `Tests allowed this session` when applicable. Its panel lists project-session and task-exact grants separately, with revoke controls and expiry. Keep it legible beside Pause without widening the whole composer.
5. Show authorized reruns as ordinary visible CheapOS work. When a command does not match, explain the specific reason returned by the controller, such as a new test runner or another project, and request only the needed approval.
6. Use the same reusable approval rendering/action logic for Chat and Activity so the two surfaces cannot drift.

## Acceptance

Browser fixture: one approval, focused unittest run, different supported selector, checkpoint review, same-project new chat, and follow-up without repeat prompts. New command/runner asks. Revoke and restart cause the next eligible run to ask. Keyboard/small-window layout works; streams, drafts, and Pause remain usable. The interface never displays an exact-command grant as project-wide.

## Validation / limits

Run T09 permission tests and relevant presentation tests. Record the browser sequence and number of permission prompts. No permanent trust choice, hidden auto-approval, pytest/npm profile, or commit-policy changes. Update README/docs execution instructions to describe the actual shipped scopes.

## Completion record

Status: Todo

- Behavior delivered: —
- Acceptance evidence: —
- Commands and results: —
- Browser scenarios and results: —
- Remaining limitations: —

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
