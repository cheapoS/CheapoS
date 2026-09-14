# T62 — Bind planner requests to the authorized connection

Status: Ready
Priority: P1 — connection and access correctness
Depends on: current dedicated planner implementation
Size: S/M
Planning baseline: `db774c7`, September 14, 2026

## Outcome and reproduced failure

Planning uses the exact connection and model access authorized for the task.
It cannot bypass endpoint, connection revision, capability, or included-access
checks because its role is `planner`.

The review reproduced a full `Engine.request(..., role='planner',
purpose='branch_planning')` with synthetic providers: the captured gateway was
`http://127.0.0.1:20128/v1`, but the provider factory received a configuration
for port `20129`. The same guard rejected that endpoint for a reviewer.
No real network request was made. The new `role != 'planner'` condition in
`access_policy.guard` skips the binding checks; catalog eligibility alone does
not establish authorization for the endpoint actually used.

## Read first

[access_policy.py](../../cheapos/access_policy.py) (`guard`, `bind_provider`),
[engine.py](../../cheapos/engine.py) (`request`, `_perform_request`),
[routing.py](../../cheapos/routing.py) (`setup_task`, `select_remote`), and
[test_access_policy.py](../../tests/test_access_policy.py).

## Implementation work

1. Trace configuration from task creation through the final dispatch boundary.
   Remove the planner exemption and correctly bind eligible planner selections;
   simply restoring a guard without preparing the binding would break fallback.
2. Validate the actual selected endpoint, model, and captured connection revision
   before reservation/dispatch. Preserve public-free and operator-included access
   distinctions and the existing rules for manual provider configurations.
3. A stale or different connection must produce a specific setup/access action.
   Do not silently authorize the new connection, copy a fresh policy over the
   saved one, or dispatch to a fallback endpoint because its model ID matches.
4. Keep probe requests subject to the same policy. Config overrides, retries,
   and fallback resolution must not provide a second bypass.
5. Preserve monetary guards. Choosing a stronger planner is not permission for
   paid escalation; explicit manual paid configurations still follow the existing
   operator-authorized budget rather than a new blanket prohibition.

## Acceptance and focused validation

- A correctly bound free planner and an explicitly included planner work.
- Wrong endpoint, stale revision, missing required binding, revoked included
  model, and absent tool support fail before provider dispatch.
- A matching catalog ID at another endpoint does not pass authorization.
- Existing worker/reviewer access checks retain their behavior.
- Reuse small access-policy dictionaries and one synthetic provider-factory
  dispatch case. Inspect the selector plan and run affected access/routing cases;
  do not add a live gateway or full unattended run. Measure any new cases.

## Completion record

Pending. Record implementation commit, actual validation and timings, and any
remaining limitations. Update TASKS.md; commit only this card's scoped changes.
