# T76 — Visible progress after approving an unattended plan

Status: Complete — focused startup feedback fix, September 14, 2026
Depends on: T70, T74, T75
Size: S
Baseline: `e2b04cc` on main

## Report and diagnosis

The operator saw roughly 30 seconds of apparent inactivity after accepting a
plan. This was an observed UX delay, not a measured provider latency breakdown.

Two frontend gaps contributed to the problem:

1. Start discarded the task returned by the server and cleared the pending
   message before fetching the current run. The previous proposal could remain
   visible after execution had been accepted.
2. Every task refresh waited for startup, gateway, readiness, and sidebar fetches
   in sequence. A slow gateway check therefore delayed both initial task state
   and later worker output; it also delayed the next polling cycle.

## Implemented behavior

- Keep the existing immediate dialog dismissal. Show pending server confirmation
  and elapsed waiting time inside the owning cheapoS reply. Hide the redundant
  Review & start action while submission is pending or its outcome is unknown.
- Apply the actual Start response before clearing pending feedback. Lost-response
  reconciliation also publishes the saved task, including a saved pause. A
  fallback acknowledgement remains if the accepted task has not been loaded.
- Refresh the selected task independently of connection/sidebar work during
  polling. Only one shared connection/sidebar refresh is in flight at a time;
  a held gateway request does not accumulate more gateway requests or block Chat.
  Explicit refresh callers still wait for the shared ancillary refresh.
- Ignore stale responses that would overwrite a newer Start result or a different
  selected chat. A late acknowledgement cannot replace a newer saved task state.
- Before the first item is selected, show “Your plan is approved. I’m preparing
  the first item” and a live elapsed status. Later item transitions keep their
  existing wording. Actual item/model events and streams take over when present.
- Keep the existing Pause control available once the server confirms running.
  Persisted pause/failure state removes live progress and shows saved diagnostics.

Changes are in `dist/app.js`, `dist/branch_ui.js`, and `dist/guidance.js`.
Authorization, budget, model routing, retries, test permissions, and backend
execution are unchanged. The UI does not fabricate milestones, completion,
provider congestion, queue position, or an ETA to fill the quiet interval.

## Focused validation

`python3 -B scripts/check.py --plan` selected frontend syntax checks, whitespace
validation, and the existing JavaScript suite. `python3 -B scripts/check.py`
passed all **139 tests in 99.156 ms** (Node suite time), plus syntax/whitespace
checks. No Python suite or live model calls were needed.

Six new deterministic cases use controlled promises, tiny saved task objects,
a VM of the actual renderer/polling functions, and a supplied timestamp. Measured
individual runtimes: 0.085, 0.088, 1.045, 0.493, 0.572, and 0.736 ms. They cover
accepted-state publication, lost-response reconciliation into a pause, polling
through a stalled gateway, stale/task-switch protection, startup action rendering,
and a 30-second quiet interval followed by output and pause. One existing item
transition fixture now explicitly includes a previously committed item.
No real-time sleep, new Git workflow fixture, or slow test was introduced.

## Browser evidence and limits

Computer use exercised a disposable synthetic HTTP fixture serving the real
assets at a separate localhost port. No personal task records or credentials
were used. The gateway response was held unresolved throughout:

- Start closed the proposal immediately, showed pending confirmation and a timer
  (observed advancing from 0s to 10s), and removed duplicate approval controls.
- Releasing only the Start response immediately displayed the accepted first-item
  wait, elapsed time, working indicator, Details, and the composer Pause button.
- Delivering synthetic worker output updated the actual item reply while the
  gateway was still held. Details displayed the worker model and streamed text.
- A saved synthetic runner failure replaced live progress, exposed its concrete
  error, and survived reload. The corrected browser run logged no rendering errors.

The browser pass caught a startup-renderer variable error during iteration; it
was fixed, covered by the actual-renderer test, and the flow was rerun from a
fresh proposal before completion.

This fixes feedback and client-side refresh blocking. It does not claim a faster
model, quantify the original 30 seconds, or add finer backend workspace/probe
milestones. Backend initialization timings and live provider qualification were
not exercised; existing startup/recovery safeguards remain in place.
