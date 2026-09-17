# Unattended startup acknowledgement

Start saves the inspected plan's authorization and returns a receipt before
repository setup runs. The response means **approval saved**, not that setup or
implementation has finished. Expensive source checks no longer hold the HTTP
request or the engine lock throughout startup.

The same task runtime owns setup and execution, reserving the unattended slot
before acknowledgement. Repeating Start for that proposal returns the existing
run. A lost response can be reconciled from saved task state without another
launch. Existing synchronous controller callers retain their default behavior.

Chat shows persisted stages inside the active cheapoS reply:

1. Approval saved
2. Verifying task copy
3. Preparing branch
4. Preparing approved checks
5. Selecting worker

Pause remains available. A stopped or failed setup retains its approval and
diagnostic, with an explicit recovery action. Restart marks unfinished startup
as interrupted; it does not execute work automatically or renew allowances.
Source identity, base revision, feature ownership, command scope, readiness, and
snapshot checks must still pass before execution. Saving approval does not
override a stale base, changed snapshot, expired proposal, or revoked authority.

## Batched snapshot verification

Each snapshot verification reads the captured Git objects through one
`git cat-file --batch` process. The parser checks each object identity, type,
size, framing, and total response length before comparing binary content and
executable modes. Both existing snapshot verification passes remain in place.

A read-only measurement against this checkout's committed manifest fetched
477 files (5,805,478 bytes) in one process in 0.0613 seconds. The previous
verification launched one process per file, twice during startup: 954 blob-read
processes for that manifest. This timing covers blob retrieval only, not total
startup or model selection. Provider availability can still delay selection.

## Validation — September 17, 2026

- Five new deterministic unit cases cover cancellation, saved failure,
  authority/restart handling, binary/duplicate/empty blobs, and malformed batch
  responses: **0.003 seconds combined**. No new full workflow or timed-wait test.
- Existing HTTP cases now hold setup behind a synchronization event and prove
  Start and task polling return before it is released; repeated Start launches
  once. The existing successful-start case took 5.927 seconds, including its
  existing temporary Git setup. All five HTTP cases passed.
- Focused controller, authorization, run state, planning race, command scope,
  admission, and storage checks: 41 passed, one pre-existing fixture error in
  17.679 seconds wall time. The failing
  `test_manual_mutations_cannot_change_branch_contract` omits `task['limits']`
  and raises `KeyError: 'limits'`. The same failure was reproduced against
  unchanged HEAD (`c830b26`); this change does not alter that fixture or engine
  limit handling.
- Existing workspace coverage: all 11 cases passed, including snapshot tamper
  and branch ownership cases. All 242 JavaScript tests passed (0.214 seconds).
- Computer-use check on an isolated local server: reviewed the fixture plan,
  clicked Start, observed immediate return to chat and all startup stages,
  reloaded while setup was held and retained progress, and paused startup.
  Model execution was replaced with a deterministic stub; no provider request
  or personal task was used. Header and timer corrections are also covered by
  JavaScript assertions.

The full Python suite was not run: validation followed the change-scoped policy
in CONTRIBUTING.md. The user's running application was not restarted.
