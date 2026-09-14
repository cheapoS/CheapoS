# T68 — Show planner usage and identity consistently

Status: Ready after dependencies
Priority: P2 — trustworthy accounting and observability
Depends on: T65, T66
Size: S/M
Planning baseline: `db774c7`, September 14, 2026

## Outcome and reproduced failure

Operators can see which model planned the job and how much usage planning took,
including when the same model serves as planner and reviewer.

Raw task usage now has a planner bucket, but metrics and the UI still aggregate
worker/reviewer/coordinator. A planner-only task with 100 tokens reproduced an
`accounted_total` of zero. The overall monetary total already includes planner
cost; preserve it. Routing traces also label an unrecognized planner role as
`unknown`, and model-pool evidence readers omit the new role.

## Read first

[metrics.py](../../cheapos/metrics.py),
[branch_budget.py](../../cheapos/branch_budget.py),
[routing_trace.py](../../cheapos/routing_trace.py),
[model_pool.py](../../cheapos/model_pool.py),
[app.js](../../dist/app.js), and existing metrics/routing trace UI tests.

## Implementation work

1. Audit role allowlists and aggregate readers. Include planner request counts,
   accounted tokens, per-role cost, and identity wherever the app presents a
   total or breakdown. A shared model can have separate role rows without
   counting the same request twice.
2. Preserve provider-reported, estimated, uncertain, and historical attribution.
   Do not reconstruct missing tokens from prices or turn missing history into
   zero. Include failed attempts/reservations under existing accounting rules.
3. Retain actual planning identity through proposal preparation and run start;
   do not display the current global model as if it made historical requests.
4. Recognize planner routing traces and correctly associate attempts. Check
   model-pool read/write role sets: `plans_completed` must not influence ranking
   unless a defined, durable validated-plan outcome actually populates it.
   Tool-probe success or configuration alone is not plan completion evidence.
5. Update metrics documentation and any exported schema description. Keep
   existing worker/reviewer completion semantics and monetary guards intact;
   this is not a budget-policy redesign or a new savings claim.

## Acceptance and focused validation

- A planner-only 100-token fixture reports 100 total tokens and one dispatched
  planner call; a mixed-role fixture totals each request once.
- Retries, uncertain usage, old tasks, and zero-cost planning retain truthful
  attribution. Total dollars do not change merely because a row is displayed.
- Session details and traces show Planner with the actual model and usage.
- Pure aggregate/trace fixtures and existing JS render tests cover the data
  paths. Reuse a synthetic UI task for inspection; no inference or benchmark.
  Record new-case timings, update this card/TASKS.md, and commit scoped work.

## Completion record

Pending.
