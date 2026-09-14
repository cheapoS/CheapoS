# T50 — Make transport fallback explicit, scoped, and fully accounted

Status: Not started
Priority: High
Depends on: current provider/streaming implementation
Size: M
Planning baseline: `4b6ed68`, September 14, 2026

## Outcome

A known incompatible reviewer route can use a complete JSON response while
cheapoS visibly remains at work. If a streamed request needs an allowed retry,
each network attempt has its own accounting, authorization checks, and outcome.
Transport recovery cannot bypass Pause or consume an unrecorded second request.

## Current evidence and files

Read [engine.py](../../cheapos/engine.py), especially `request`, `_request`,
reservation/usage handling, and the `stream_error` fallback; then read
[providers.py](../../cheapos/providers.py), [streaming.py](../../cheapos/streaming.py),
[metrics.py](../../cheapos/metrics.py), [branch_budget.py](../../cheapos/branch_budget.py),
and [served_identity.py](../../cheapos/served_identity.py).

`ChatProvider.streams_output` currently disables streaming for any model name
containing `gemini`, regardless of role. The engine also calls `provider.complete`
directly after `stream_error`, under the first attempt's reservation and metrics
record. That second dispatch does not pass through the ordinary request boundary.
The reported trial improvement is useful evidence for a workaround, not proof
of universal Gemini incompatibility or 100% future stability.

## Work

1. Represent transport choice explicitly at the request/provider boundary using
   endpoint/model identity, role or purpose, and tools present. Replace the broad
   name-substring rule with a narrowly documented compatibility rule or explicit
   route preference. Preserve the known reviewer workaround while scoping it;
   do not disable unrelated worker/chat progress or force live discovery probes.
2. Route any fallback attempt through the same guards as a normal dispatch:
   access policy, remaining spend, reviewer/request allowances, current authority,
   and user cancellation. Reserve before each actual attempt. Keep retry count
   finite under the existing recovery policy; do not add recursive retry loops.
3. Finalize the first attempt as failed/interrupted, retaining known usage or its
   uncertain reservation. Create a distinct attempt ID for the fallback, linked
   to the first. Capture transport, role/purpose, dispatched and served model,
   timing, and reason separately. Do not double-count a logical worker turn just
   to record two network requests, or undercount two billable requests as one.
4. Define which structured failures justify changing transport. A generic
   `stream_error` is insufficient evidence that retry will help. Cancellation,
   quota/auth failures, model refusal, and exhausted budget must keep their own
   handling. Never repair malformed tool JSON into an executable call.
5. Preserve final usage frames and incomplete-tool protections. An unsuccessful
   stream executes no tools. Only a fully validated successful response may
   execute its returned calls, once. Ensure probe fallback keeps the brief
   request's timeout/output contract rather than using ordinary long defaults.
6. Emit a visible event such as “The streamed reply failed; retrying this reviewer
   without streaming” only when that retry is actually dispatched. For a normal
   non-streaming call, expose a real waiting/request state with elapsed time and
   Pause. Do not fabricate thinking tokens or leave stale streaming text active.
7. Include transport compatibility in relevant readiness-cache identity if its
   meaning changes. A probe from a different transport contract cannot silently
   establish current compatibility. Do not clear unrelated completed-work history.

## Acceptance

- Stream failure followed by permitted JSON success produces two attempt records;
  first-attempt usage/reservation survives and second-attempt usage is counted.
- Insufficient remaining spend, revoked authority, Pause, or exhausted retry
  allowance prevents the second network call. Restart cannot renew that allowance.
- Failure of both attempts retains both outcomes and a specific operator message.
- Returned partial calls are never executed, and the successful call is not
  executed twice. Missing usage remains unknown, not zero.
- A known reviewer compatibility rule does not globally disable unrelated
  streaming. Probe deadlines remain brief during any allowed fallback.
- The UI shows honest activity while awaiting non-streaming output.

## Focused validation

Start with the selector plan. Prefer scripted providers, `BytesIO` SSE frames,
injected clocks, and dispatch counters. Reuse `test_streaming.py`,
`test_metrics.py`, `test_branch_budget.py`, and affected recovery cases. New
accounting/selection cases should avoid real network calls, sleeps, and full
branch runs. Keep existing integration cases where changed boundaries need them.
Report new-case timings; disclose any proposed heavy addition before adding it.

## Completion record

Record supported transport scopes, retry/error rules, per-attempt accounting,
focused checks and timing, and visual verification or its explicit limitation.
No paid model trial or change to the operator's selected access policy is part
of this card.
