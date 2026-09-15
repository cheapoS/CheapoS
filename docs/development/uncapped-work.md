# Operator-controlled work allowances

Open the budget button beside the composer (for example, **Free only · Custom
90 min**) or **Inspect work limits** on a paused run. Select **Uncapped work · ∞**
and save. Resume the same saved run when ready. Saving alone does not start work.
The choice is also available in unattended proposal review and new-chat defaults.

Uncapped work removes cumulative worker-turn, request, tool-action, iteration,
reviewer-token and working-time caps, including checkpoint turn ceilings. It uses
an explicit boolean, not a huge numeric allowance. Usage and elapsed work remain
counted across pauses and restarts. Existing finite worker-turn allowances can
also exceed 200; finite values still need to fit the serialized numeric contract.

Spending caps, automatic-routing charge checks, authorized models, command
permissions, independent review, evidence validation and bounded stalled-work
recovery still apply. Changing work allowances neither approves a command nor
renews recovery attempts. Per-response output limits, verification command
timeouts and provider transport limits remain independent controls. A model or
provider may still stop a request at its own limits.

Qualification **measurement mode** retains its separate behavior: it also omits
the verification deadline and uses provider-default output allowances on zero-rate
requests. Ordinary uncapped work does not enable those measurement overrides.
Switching an existing measured run back to bounded work removes both work-cap
exemptions.

For unattended work the choice is part of the approved plan. A trusted operator
update on a paused run updates the durable authorization contract and records an
event. Neither planner output nor a task-local flag can expand approved branch
authority. Planning remains subject to its original allowance; new-chat uncapped
defaults are applied to the proposed execution plan for inspection before Start.

## Validation, 2026-09-14

- Six new deterministic Python cases took **0.002 seconds** together. They
  cover explicit input, authority, retained usage, restart serialization,
  bounded-mode restoration, active-run exclusion, and money/output caps.
- Reused existing preference and branch-start coverage to check real persistence
  and authorization after restart, without another agent/Git workflow test.
- Two new JavaScript cases exercise the actual limit form/serialization and saved
  branch mode. The frontend check set passed **183 cases in 0.116 seconds**.
- Disposable computer-use check: a task with 201 worker turns and 196 requests
  was paused. The operator selected uncapped work, saved, resumed, and renewed
  only the displayed expired test permission. The task reused its saved passing
  check, completed independent review, committed one item, and passed final
  integration review. It ended at **202 worker turns, 201 requests, $0.00**, ready
  for the operator's merge decision. Nominal saved caps remained 200/196; usage
  was not reset. All model responses were deterministic local fixtures.

No personal task or paid model was used as a test fixture. No heavy regression
test was added. Another concurrent edit replaced `engine.py` during validation;
the conflicting edits were removed at the operator's request and affected checks
were rerun against the restored implementation.
