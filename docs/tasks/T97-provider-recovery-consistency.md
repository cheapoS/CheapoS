# T97 — Continue through provider failures in every request path

Status: **Completed**, September 18, 2026. Priority: **P1**.
Parent: [T94](T94-operator-limits-and-autonomous-completion.md).
Can start independently; coordinate the HTTP error contract with T96. T98 builds
on the availability behavior here.

## Problem and evidence

Baseline `49cbecb` has three reproduced gaps:

- Invalid streamed tool indexes and response bodies over 4 MB can raise an
  uncoded `ProviderError`, bypassing general routing recovery.
- Recoverable proxy 5xx errors such as `http_524` are absent from the shared
  outage/transient classifications. A 524 becomes an invalid-response quality
  failure, potentially spending quality handoffs and extending cooldown.
- Reviewer identity recovery calls `_request` directly for replacements. A 503
  from its first candidate escapes even when a second eligible independent
  candidate is available. An existing test preserves this exception but does
  not prove that review finishes.

## Change

1. Give known malformed/oversized response and transport failures stable codes.
   Distinguish output representation/validation problems from outages and access
   failures; not every normalized error is an outage.
2. Share the transient/outage classification used by route health, scheduling,
   and substantive review allowance. Audit all recognized recoverable proxy 5xx
   statuses instead of special-casing only 524.
3. Route replacement-reviewer availability through the authorized scheduler.
   Continue with another independent candidate or wait for an actual availability
   check; persist selected/dispatched/uncertain state before proceeding.
4. Preserve the exact review candidate, completed coverage, findings and valid
   verification. Do not send finished implementation back to a worker because a
   reviewer transport failed.
5. Keep safe diagnostics and truthful activity: waiting is not a running model
   request. Respect Retry-After and model/provider/connection scope; prefer an
   eligible other provider when the current provider is unavailable.

Ambiguous authentication failures remain connection prerequisites. Do not bypass
credentials, pins, free-only placement, spending, or independent reviewer
identity. Count every dispatch; outages do not consume model-quality allowances
but their usage is still accounted. No partial tool batch may execute.

## Implementation starting points

`cheapos/providers.py`, `streaming.py`, `provider_recovery.py`, `route_health.py`,
`model_pool.py`, `route_schedule.py`, `reviewer_recovery.py`, `transport.py`, and
`engine.py` request callers. Inspect planning/item/final-review exception owners.

Extend `tests/test_streaming.py`, `tests/test_route_health.py`,
`tests/test_route_schedule.py`, `tests/test_transport.py`,
`tests/test_reviewer_recovery.py` and existing final-review recovery fixtures.
The current `test_access_and_outage_errors_are_not_mislabeled_as_identity_failures`
should preserve correct classification while new coverage proves continuation.

## Acceptance

- [x] Identity recovery's first replacement returns 503; a second authorized
  independent reviewer completes review without operator input or repeated checks.
- [x] Proxy 524 is transient, does not damage model-quality ratings, and causes
  a useful authorized handoff/wait rather than an arbitrary task stop.
- [x] Uncoded malformed/oversized cases receive specific repair/handoff behavior;
  complete-envelope validation still prevents partial tool execution.
- [x] Temporarily unavailable pools wait with a scheduled check and cancellation.
  Permanently missing access is not disguised as endless quota waiting.
- [x] Auth ambiguity, upstream-only refusal, pins, independent identity and
  spending boundaries retain distinct, enforced behavior.
- [x] Restart between saved selection and dispatch continues once; uncertain
  dispatch remains accounted and is not blindly duplicated.
- [x] Representative planner, worker, item-review and final-review call paths
  use the same classifications and retain their saved context.

Use scripted responses, fake clocks and existing fixtures. No real cooldown
sleeps or live model calls. Follow T94's scoped validation and cost rules.

Focused provider, streaming and reviewer-replacement tests: 30 passed in 0.674s.
New cases are pure scripted responses; no cooldown sleeps or inference.

Validation: [T94–T100 completion report](../development/operator-limits-validation.md).
