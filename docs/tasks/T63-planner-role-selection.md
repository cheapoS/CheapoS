# T63 — Preserve working routes when a planner is configured

Status: Complete
Priority: P1 — worker/reviewer availability
Depends on: T62
Size: S/M
Planning baseline: `db774c7`, September 14, 2026

## Outcome and reproduced failure

Configuring a planner must not make an otherwise working worker/reviewer pair
unavailable. Reviewer independence follows the models that authored the patch.
A model used only for read-only planning may also review it.

At the review baseline, remote/delegate setup pins the configured reviewer as
planner. `select_remote` excludes all models in `task.providers`. With eligible
models A and B, configured worker A and reviewer B, the worker selects A and
reviewer selection pauses because B is already the planner. Removing the unused
planner entry makes the same two-model fixture select B successfully. This also
affects ordinary chats that never invoke planning.

## Read first

[routing.py](../../cheapos/routing.py),
[model_pool.py](../../cheapos/model_pool.py),
[engine.py](../../cheapos/engine.py) (automatic requests/handoffs),
[test_routing.py](../../tests/test_routing.py), and
[test_model_pool.py](../../tests/test_model_pool.py).

## Implementation work

1. Replace the blanket all-pinned-model exclusion with explicit role eligibility
   that preserves the existing worker-versus-reviewer independence rules.
2. Allow planner/reviewer reuse when planning did not author files. Preserve
   exclusion of current and previous patch authors after worker handoffs.
   Merely renaming an author as planner must not make it an independent reviewer.
3. Do not require a third model for normal chats or for a run using reviewer
   fallback as planner. Dedicated planner preferences may select a third model,
   but its presence must not unnecessarily reserve worker/reviewer capacity.
4. Apply the same policy during initial selection, replacement, cached probes,
   and resume. Preserve connection scope, cooldowns, failed-model evidence,
   probe budgets, and handoff limits; do not clear them to make selection pass.
5. Keep routing explanations accurate. A planning-only model must not appear
   excluded as a prior patch author. Preserve actual selected identities in
   request evidence even when one model serves two roles.

## Acceptance and focused validation

- With only A/B available, an ordinary remote chat and a delegated run can use
  A as worker and B as planner/reviewer without an availability pause.
- Configuring a third planner C also works without changing the independent
  reviewer requirement or forcing worker selection away from eligible A.
- A model that actually authored edits remains ineligible to review them,
  including after a handoff or restart.
- Use synthetic catalogs and cached successful probe observations. Exercise
  selection directly before reusing the relevant existing failover cases.
  No inference, sleeps, or new full agent workflow is needed. Report timings.

## Completion record

Completed in the scoped T63 commit. Planner-only models no longer reserve worker/reviewer capacity. Review still excludes the current worker and persisted prior patch authors, including replacement selection. Cached synthetic A/B and A/B/C selection passes without dispatch. Nine access tests passed in 0.009s (new case 0.001s). Existing routing/model-pool checks: 45/46 passed in 26.893s; the documented baseline unavailable-tool action-recovery failure remains unchanged (worker a instead of b). No inference or new integration fixture.
