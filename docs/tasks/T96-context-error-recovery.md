# T96 — Repair oversized context before changing routes

Status: **Planned**, September 18, 2026. Priority: **P1**.
Parent: [T94](T94-operator-limits-and-autonomous-completion.md).
Can start independently. T99 later centralizes output/context budget resolution.

## Problem and evidence

Two in-memory cases reproduce gaps at baseline `49cbecb`:

- An OmniRoute HTTP 400 body with machine code `context_length_exceeded` becomes
  generic `http_400` in `providers.http_failure`. The context diagnosis is lost.
- Even a correctly coded context exception enters `_request_routed`'s generic
  route-defer path before the outer worker context-repair handler sees it.

Replacing a model while resending an unchanged oversized payload does not
repair the request and can incorrectly damage route health.

## Change

1. Preserve a narrow allowlist of explicit, recognized context-error codes at
   the HTTP boundary. Retain only validated size metadata; do not expose arbitrary
   upstream text, failed generations, credentials or raw private prompts.
2. Give the current context owner the error before general availability/quality
   routing. Trace planner, worker and reviewer callers; do not create an exception
   escape in another role while fixing the worker path.
3. Produce a smaller, valid request from retained evidence. Preserve exact active
   instructions, current work, unresolved findings and complete tool exchanges.
   Keep full history by reference and distinguish projection from deleting it.
4. Retry only after a material payload/strategy change. If irreducible context
   cannot fit, select a larger eligible route where authorized. Respect pins,
   spending and reviewer independence; unknown capacity stays unknown.
5. Record safe before/after size and strategy metadata. Keep every dispatched
   request accounted and retain unresolved reservations.

Do not globally truncate prompts, discard review coverage, claim context capacity
from a model name, or classify arbitrary HTTP 400 responses as context failures.
Use current output-budget behavior here; integrate T99's resolver when available.

## Implementation starting points

`cheapos/providers.py`: `http_failure`; `cheapos/engine.py`: `_request_routed` and
worker context recovery; `cheapos/context_budget.py`, `context_compaction.py`,
`context_evidence.py`, `model_pool.py`, and role-specific request callers.

Extend `tests/test_context_budget.py`, `tests/test_context_compaction.py` and
focused HTTP/transport fixtures. The existing
`test_only_explicit_context_errors_trigger_retry` verifies a helper, not the
whole HTTP → routing → compaction path.

## Acceptance

- [ ] A synthetic explicit context rejection passes through HTTP parsing and
  routing to repair; the next smaller request succeeds with no route-quality
  penalty, manual Resume or repeated implementation.
- [ ] Irreducible context selects a known larger authorized route when available;
  a pinned route or unavailable authority is not silently bypassed.
- [ ] Exact instructions, complete tool pairs, current checks and reviewer
  coverage survive compaction, handoff and reload.
- [ ] Generic 400/auth/tool-validation errors retain their own classifications.
- [ ] Repeated rejection of an unchanged payload changes strategy instead of
  emitting the same request indefinitely; partial tools never execute.
- [ ] Each dispatched attempt is counted once, including failed/uncertain usage.

Use small synthetic messages, fake responses and saved-state round trips.
No production tasks or provider calls. Follow T94 validation and cost rules.
