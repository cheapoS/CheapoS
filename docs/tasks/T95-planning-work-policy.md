# T95 — Apply the selected work policy during planning

Status: **Planned**, September 18, 2026. Priority: **P1**.
Parent: [T94](T94-operator-limits-and-autonomous-completion.md).
No prerequisite among the new audit tasks. T98 and T99 build on this contract.

## Problem and evidence

At audit baseline `49cbecb`, `BranchController.plan` captures an explicit
`uncapped_work` choice in `planning_request` but creates the live draft with
only the measurement flag. `_finish_plan` adds Uncapped after proposal success.
`measurement.enabled` gives branch-plan state precedence over task-local flags.
A small in-memory reproduction therefore sees the operator's Uncapped choice
in the request while the live planner remains bounded.

The existing Uncapped documentation explicitly describes planning's original
allowance. This is a product-contract correction, not evidence that the
behavior was a newly introduced regression. Explicit measurement/development
modes can mask the mismatch.

## Change

1. Capture the trusted operator's effective work policy before the first
   planning request. Carry it into the live draft and proposed execution plan.
2. Restore the same policy on planning continuation/restart. Use the saved
   snapshot and revision, not current global defaults or model-proposed values.
3. Preserve cumulative requests, usage, elapsed work, evidence and failed
   strategies across planning repair, handoff and continuation.
4. Keep bounded work and spending enforcement. An Uncapped task-local flag or
   planner response cannot expand an already authorized branch policy.
5. Update the planning/Uncapped documentation to match the implemented behavior.

Do not change planner repair/discovery counters here; T98 owns their recovery
semantics. Do not introduce the full new settings schema; T99 owns that migration.

## Implementation starting points

- `cheapos/branch_controller.py`: `plan`, `_finish_plan`, `restore_planning_allowance`.
- `cheapos/measurement.py`, `cheapos/branch_budget.py` and existing authority receipts.
- `cheapos/settings_adapter.py`, `cheapos/task_settings.py` for saved policy capture.
- Existing tests: `tests/test_uncapped_work.py`, `tests/test_measurement.py`,
  `tests/test_branch_planner.py`, `tests/test_task_settings.py`.
- [Current Uncapped documentation](../development/uncapped-work.md).

Verify symbols against the implementation checkout before editing.

## Acceptance

- [ ] An explicitly uncapped draft exceeds a tiny fixture's nominal planning
  allowance, repairs its proposal and produces an approvable plan without Resume.
- [ ] A bounded draft still enforces its selected budget and saves a continuation.
- [ ] Planner output cannot grant Uncapped or broader spending/model authority.
- [ ] Changing defaults or another chat does not alter a saved planning policy.
- [ ] Serialization/reload and planning retry preserve the choice and all usage;
  model requests are not duplicated by restoration.
- [ ] Ordinary Uncapped and explicit measurement retain their distinct existing
  output/check semantics until T99 deliberately migrates those controls.

Use a mocked planner/ledger and in-memory policy fixtures, extending existing
coverage. No live provider, new multi-item Git run or real wait is necessary.
Follow T94's validation and commit rules and report added test runtime.
