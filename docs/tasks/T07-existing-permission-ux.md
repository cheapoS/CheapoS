# T07 — Expose existing session approval and diagnose repeat prompts

**Depends on:** none. **Size:** S. **Result:** the current exact-command grant becomes discoverable, with evidence about any actual duplicate-approval bug.

## Read first

`Engine.approve_check`, `session_permissions`, `clear_session_permissions`, `checks`, `tests/test_permissions.py`, and the pending-approval blocks in `renderChat`/`renderActivity` plus `sessionPermissions()`.

## Implementation

1. Reproduce the existing contract with a scripted provider: approve an exact command for the session, run it again, pause/resume, and run it in a follow-up. All should reuse the grant in the same task copy and server lifetime.
2. Test differing argv, a new workspace, another chat, and restart. Those currently ask by design. If the identical case asks twice, fix the concrete key/state/approval-ID bug and add its regression. Do not claim changed commands are that bug.
3. Make `Allow this command for this session` the primary button in both Chat and Activity; keep Run once and Decline. This wording must remain exact-command scoped until T09/T10 exist.
4. Show a discoverable session-permissions control by the composer when grants exist. Clicking lists the commands and revocation action, reusing the existing endpoint. Show the expiry/scope clearly: `This chat · until cheapoS restarts`.
5. For an automatic authorized rerun, show `Running tests · allowed for this session` with the real command/output in Details. If a new command asks, show the concrete difference or scope reason when known; do not invent an explanation.
6. Do not poll the permissions endpoint on every keystroke or stream token. Refresh after grant/revoke/task selection and relevant state changes. Preserve the existing approval ID validation.

## Acceptance

Identical repeated commands produce one prompt. Changed commands still ask. Chat and Activity use matching labels and behavior. Revoking causes the next run to ask; it does not kill a running process. Live output and Pause remain visible. The final handoff states which repeated-prompt cases were reproduced, not an unverified blanket claim.

## Validation / limits

Run `test_permissions.py` and relevant HTTP/JS checks; browser-test the two approval surfaces and revocation using a fixture. No project-wide grants, arbitrary prefix whitelist, persistent trust, limit increases, or automatic approval on behalf of the user.

## Completion record

Status: Done

- Behavior delivered: Exact-command session approval is primary in Chat/Activity; composer exposes grants and revocation; authorized reruns are visibly labeled; permission refresh is keyed to task/workspace/status/approval changes, not tokens or keystrokes.
- Acceptance evidence: No identical-command duplicate reproduced. Exact argv survives real pause/resume and follow-up; changed argv/workspace/chat, revocation, and restart ask by design. Approval ID checks remain intact.
- Commands and results: 7 permission tests and 61 JavaScript tests passed; syntax and diff checks passed. Existing permission HTTP contract passed in T06.
- Browser scenarios and results: Deterministic local provider; matching Chat/Activity primary labels; granted from Activity; later checks ran visibly without prompts; composer grant control showed exact command and expiry; revocation removed control. No external model requests.
- Remaining limitations: Scope remains one exact command and task workspace until restart. Project-wide profiles follow in T08–T10.

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
