# T16 — Cancelable waiting for a free route

**Depends on:** T15. **Size:** M. **Result:** a known provider cooldown does not demand repeated Resume clicks.

## Read first

`FreeModelPool` cooldown state, `select_remote`, `RoutingPause`, provider Retry-After handling, runtime stop/deadline checks, storage restart handling, and active-status lists in frontend/guidance.

## Implementation

1. Return structured route-unavailable information: affected scope, earliest eligible retry time when known, and whether waiting fits the remaining task envelope. Avoid claiming every model failed when the provider is cooling down.
2. Offer a user-visible `Retry when available` action when appropriate. Once selected, wait cancelably under the existing run, bounded by its remaining time and handoff/probe allowances. Do not reset counters each time the cooldown expires.
3. Represent waiting explicitly and update all relevant active-state/UI/restart handling. A waiting run must be discoverable and pausable; honor the app's existing single-active-task policy rather than spawning invisible background jobs.
4. Use interruptible waits and re-check eligibility before probing. Do not hammer the provider every UI poll or treat a cooldown deadline as proof the model is healthy.
5. Show a countdown/status inside cheapoS with `Pause` and an option to inspect Models. If no retry time is known, do not fabricate one; offer a bounded manual retry path.
6. When the outer deadline/attempt allowance expires, stop once with preserved work and a concrete message. On server restart, mark interrupted and require explicit continuation; do not auto-dispatch saved tasks.

## Acceptance

Fake-clock fixtures: no requests before Retry-After, exactly the allowed probes after expiry, pause cancels waiting, deadline ends waiting, restart does not resume, and a successful candidate continues from the saved stage. Pending review must not cause the worker to redo edits. Browser status must show waiting rather than generic thinking.

## Validation / limits

No OS scheduler, recurring automation, external monitor, real long sleeps in unit tests, or request storms. No automatic wait beyond the operator's task envelope. Continue enforcing free/local/manual placement and distinct reviewer identity where required.

## Completion record

Status: Done

- Behavior delivered: Structured route-unavailable scope/retry time/remaining-envelope eligibility; explicit Retry when available starts cancelable waiting in the same active task. Countdown, Pause and Models controls; eligibility rechecked after expiry. Three scheduled waits and four probes per role per request, with existing handoff/time/spending caps. Restart interrupts and never auto-dispatches. Unknown Retry-After stays unknown.
- Acceptance evidence: Eight cooldown fixtures cover no work before expiry, one probe after expiry, stop/deadline cancellation, unknown/over-budget refusal, active-slot exclusion, restart retention, probe exhaustion, and pending review resuming without worker/check replay. Fake clocks avoid long sleeps.
- Commands and results: Initial routing/recovery set: 52 passed (54.874s). Final wait/model-pool/probe-bound set: 29 passed (30.805s). HTTP: 29 passed (30.691s). JavaScript syntax and 64 presentation tests passed; git diff --check passed. Logs /tmp/cheapos-t16-*.log.
- Browser scenarios and results: Dedicated scripted server at port 51027 offered Retry when available for a known provider cooldown. Waiting showed a live eligibility countdown, no model request running, Pause and Inspect Models. Pause canceled the wait. A later explicit retry continued the saved request to Ready for your message. Corrected the live step countdown to update with the main countdown.
- Remaining limitations: A countdown is next eligibility, not a health guarantee. Unknown provider retry times use manual recovery. A request exhausting waits/probes needs a changed instruction or operator decision; Resume does not reset those counters. No background scheduler or paid/local fallback added.

Before implementing, read [TASKS.md](../archive/TASKS.md) for the shared contract. Update this record and the matching board row when complete.
