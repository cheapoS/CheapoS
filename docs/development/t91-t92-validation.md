# T91 / T92 qualification — September 17, 2026

T92 landed first on local main at cffdd46, so integration recovery was available
before the settings work. Followups retain explicit cancellation and allow a new
operator request, and expose an Interactive conflict-resolution comparison.

T91 captures settings once, separates app/project/chat scopes, preserves approved
plan authority, and supports durable paused-task Apply & continue. Active-task
changes use Pause to apply. Credentials and command/merge approvals remain in
existing owners. Fresh installations use automatic free remote work defaults;
startup greeting authorization remains separate. Migrated settings are retained.

## Focused validation

- New settings store, adapter, task settings, runtime and integration-preparation
  modules: **51 tests, 0.085 seconds** combined. These use small deterministic
  fixtures; no live model calls or deliberate waits.
- Existing settings/preferences/startup/work-limit and selected routing cases:
  **81 tests, 1.165 seconds**. Startup/fresh-install changes received additional
  focused checks before integration.
- Existing branch authorization, start and reprepare coverage plus integration,
  settings adapter and startup cases: **63 tests, 10.152 seconds**.
- Scoped settings HTTP checks exercise trusted mutations, stale revision (409),
  idempotent replay, unregistered projects and static assets. The combined three
  HTTP cases took 0.295 seconds; one legacy fixture then needed explicit Manual
  placement and distinct reviewer selection, and passed in 0.637 seconds.
- All **257 JavaScript tests passed in 0.194 seconds**. Disposable browser fixtures
  exercised dirty scope changes, retaining edits, exact-chat save, the shared
  connections form, Update & resolve, resolution comparison, and a 320px layout.
- Earlier T92 focused Git/HTTP checks passed; existing completion coverage took
  about 32 seconds, and HTTP/commit reconciliation coverage about 15 seconds.
  No new full Git workflow was added for T91.

These counts overlap; they are separate runs, not an additive coverage total.
The check selector was inspected; changing Engine conservatively selects 135
Python modules. Only affected checks were run, not the full suite.

## Existing failures confirmed on unchanged main

Two older routing assertions also fail at the T92-only main commit cffdd46:

- test_three_identical_reads_allow_one_answer_request_without_tools expects
  answer_pending to remain true.
- test_unavailable_tool_during_action_recovery_hands_off_without_executing_any_calls
  expects model b, but the saved result uses model a.

Both were reproduced independently on that baseline, not counted as passing and
not weakened as part of settings work. No live provider qualification was run.
