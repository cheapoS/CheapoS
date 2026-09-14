# T65 — Make the dedicated planner configurable and durable

Status: Complete
Priority: P2 — complete the planner feature
Depends on: T63, T64
Size: M
Planning baseline: `db774c7`, September 14, 2026

## Outcome and reproduced failure

An operator can choose a stronger planner independently of the worker and
reviewer, see what will handle planning, and retain the selection after restart.
The default remains a clear reviewer fallback when no dedicated planner is set.

At the review baseline, the model-list endpoint accepts `planner`, but
`Engine.configure` normalizes only worker/reviewer. Submitting all three saves
only two. Saving Connections also deletes a manually inserted planner config.
Local setup reads `local_planner`, while execution preference validation rejects
that key. No planner fields exist in the Connections UI.

## Read first

[engine.py](../../cheapos/engine.py) (configuration and preferences),
[routing.py](../../cheapos/routing.py) (`execution_from`, `setup_task`),
[server.py](../../cheapos/server.py) (configuration/model endpoints),
[app.js](../../dist/app.js) (Connections),
[startup.py](../../cheapos/startup.py), and
[readiness.py](../../cheapos/readiness.py).

## Implementation work

1. Extend validation/save/load paths to support an optional dedicated planner.
   Define omitted versus explicitly cleared values: updating other roles must
   preserve a saved planner; an explicit reset selects reviewer fallback.
   Older two-role configurations must load without manual repair.
2. Add a plainly labeled Planner selection to Connections using the existing
   provider/model controls. Show the effective fallback model when enabled;
   do not duplicate three full settings forms unless the operator expands them.
3. For local execution, accept and persist an optional installed local planner
   choice, falling back to local reviewer/model using the existing rules.
   Do not download models or start inference simply to save preferences.
4. Wire model discovery, credential availability, and startup/readiness through
   the same configuration contract. Surface missing credentials/models before
   dispatch. Follow T64's credential storage policy and never save raw secrets
   into config/task JSON.
5. Pin the effective planner and authorized access policy for a new proposal.
   Later settings changes must not silently alter an approved run. Keep manual
   versus automatic execution semantics and existing spending limits explicit.
6. Update the relevant model-setup documentation with dedicated selection,
   fallback behavior, restart persistence, and the applicable credential policy.

## Acceptance and focused validation

- Save all three roles, reconstruct Engine from the temporary data directory,
  and recover the selected planner model/endpoint without key disclosure.
- Editing only the worker/reviewer preserves a dedicated planner; explicitly
  resetting it restores reviewer fallback. Legacy two-role config still works.
- Local planner preference survives save/load, and invalid values fail clearly.
- An isolated UI pass can choose a planner, observe fallback, and reopen saved
  settings. Missing authentication is distinguishable from missing model setup.
- Prefer small configuration round trips and existing readiness/UI fixtures.
  No live requests or new end-to-end agent runs. Measure new cases, record any
  browser gap, then commit with TASKS.md and this completion record updated.

## Completion record

Dedicated planner settings support partial updates, explicit null reset, durable model/endpoint, and local_planner preferences. Connections exposes an optional expandable planner form and reviewer fallback. Three configuration cases passed in 0.011s combined with T66; JS syntax passed. Isolated browser verification passed: switch reviewer fallback to a dedicated local fixture planner, save, and reopen with the selected model retained. No inference or personal data. Keys remain memory/environment-only for direct providers; config JSON never stores them.

Readiness includes planner model/authentication state and local planner cache invalidation. Six readiness cases passed in 0.004s; new pure case under 0.001s.
