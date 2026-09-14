# T66 — Resume pre-planner tasks safely

Status: Complete
Priority: P2 — saved-task compatibility
Depends on: T64
Size: S
Planning baseline: `db774c7`, September 14, 2026

## Outcome and reproduced failure

A planning chat saved before the dedicated role existed can continue after an
upgrade without a new chat, lost usage, or widened authorization.

Old tasks contain worker/reviewer usage buckets only. A new planner request calls
`reserve`, which indexes `task['usage']['planner']` and raises `KeyError`. The new
`setdefault` in `reconcile` is too late because reservation precedes dispatch.
`BranchController.plan(..., planning_task=...)` reuses these old task records.

## Read first

[providers.py](../../cheapos/providers.py) (`reserve`, `reconcile`),
[storage.py](../../cheapos/storage.py),
[engine.py](../../cheapos/engine.py) (creation/resolution), and
[branch_controller.py](../../cheapos/branch_controller.py) (planning continuation).

## Implementation work

1. Introduce idempotent normalization at an appropriate load/request boundary
   before planner reservation. Missing new fields get compatible defaults;
   malformed existing accounting must not silently reset to zero.
2. Initialize a missing planner bucket without moving historical planning usage
   out of worker totals. Old role attribution is historical evidence; do not
   guess a retroactive split or double-count requests during migration.
3. Preserve global cost, reservations, uncertain requests, request IDs, limits,
   pause cause, captured inputs, and saved authorization. Migration must not
   renew an exhausted allowance or authorize a newly configured model.
4. Resolve absent planner configuration through the compatible, connection-bound
   fallback from T64. If policy actually changed, retain the existing clear
   requirement to inspect a fresh proposal instead of masking the change.
5. Repeated load/resume is safe and does not append synthetic calls or alter
   completed tasks merely to display a new role label.

## Acceptance and focused validation

- An old serialized planning-task shape with unchanged policy reserves and
  reconciles a synthetic planning response without `KeyError`.
- Migration performed twice preserves every historical amount and reservation;
  new planner usage is counted once and total cost stays correct.
- Missing planner fields are compatible; changed authorization remains blocked.
- Use small old/new task dictionaries, temporary save/load, and a fake response.
  Reuse existing planning continuation coverage where needed; do not add a full
  branch workflow. Report timings and update this card/TASKS.md before commit.

## Completion record

Reservation idempotently initializes an absent planner bucket before accounting. Existing malformed amounts fail clearly instead of resetting; historical totals, uncertainty and authorization remain intact. One pure reserve/reconcile fixture passed as part of four cases in 0.011s; no workflow or live model used.

Legacy policy comparison ignores only newly optional empty local_planner/planner defaults, preserving original contract shape and digest. Changed model, nonempty planner, or gateway authorization remains unequal. Pure compatibility fixture passed with configuration cases (4 tests, 0.013s).
