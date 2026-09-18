# T98 — Replace fixed repair stops with durable strategy recovery

Status: **Planned**, September 18, 2026. Priority: **P1**.
Parent: [T94](T94-operator-limits-and-autonomous-completion.md).
Integrate after T95 and T97; use T96's context diagnosis when available.

## Problem and evidence

At baseline `49cbecb`, proposal repair allows the initial response plus two
repairs per planner and two schema handoffs even in measurement mode. Discovery
has a separate six-call allowance, including failed reads. Planning can swallow
`RoutingPause` from its direct selector into a proposal stop.

The worker's third malformed call raises local `ProgressPause` except in
special development mode. The malformed count survives successful calls and
handoffs in an item. Unattended automatic workers may receive an outer rescue;
interactive/pinned paths differ. This is not proof that every unattended worker
always stops on the third error. Other no-action/unoffered-tool/read-loop paths
have their own thresholds and recovery owners.

## Change

1. Use the existing continuation policy to select the next useful action for
   planning, implementation and review. Persist a failure episode with role,
   item/candidate, evidence identity, attempted strategy/routes and outcome.
2. Keep thresholds as observations that trigger format repair, a different tool,
   focused context, optional coordinator advice, another authorized model, or an
   availability wait. Remove terminal retry-count policy hidden below Uncapped.
3. Distinguish lifetime usage from strategy-local baselines. A handoff or a
   successful unrelated call cannot erase a failure, but an old cumulative count
   must not immediately reject a genuinely new authorized strategy.
4. Preserve planning discovery evidence and failed attempts across invocations.
   Deduplicate identical failed reads; permit targeted new evidence when needed
   instead of forcing a proposal solely because six inspections were spent.
5. Reuse valid checks and completed review coverage. A real reviewer finding
   requires repair; switching reviewers cannot discard it or hunt for approval.
6. Make Resume and chat continuation call the same saved-state decision. Do not
   require a magic phrase, recreate the task, replenish allowances, or clear
   errors until the identical failed operation happens to work.

Pins remain binding. A pinned model may use different tools/techniques but cannot
be silently replaced. When availability can change, use a cancellable scheduled
wait; when every permitted strategy is genuinely blocked by missing information
or authority, identify that prerequisite. Never claim progress while doing an
unchanged infinite retry. No added paid coordinator calls for deterministic
error classification; local advice is optional and consulted only when useful.

## Implementation starting points

`cheapos/continuation_policy.py`, `branch_planner.py`, `engine.py`
(`tool_argument_feedback`, checkpoint and no-action guards),
`branch_worker_recovery.py`, `branch_review_recovery.py`,
`branch_final_recovery.py`, `progress.py`, `edit_recovery.py`, and
`coordinator_dispatch.py`.

Extend `tests/test_planner_discovery.py`, `tests/test_planner_schema_feedback.py`,
`tests/test_branch_review_recovery.py`, `tests/test_branch_final_recovery.py`,
`tests/test_edit_history.py` and `tests/test_progress_tracking.py`.
Retain the syntax-loop and progress fixes already described in T94.

## Acceptance

- [ ] Malformed planner output recovers through a changed approach/handoff and
  yields an approvable proposal without operator rescue in Uncapped work.
- [ ] Malformed worker output leads to a valid edit, check and independent review
  in interactive and unattended mode. A new strategy has its own baseline while
  cumulative usage and failure history remain visible.
- [ ] Successful unrelated/cosmetic edits do not erase an unresolved failing
  check; legitimate documentation changes still count as progress.
- [ ] A valid reviewer rejection returns to focused repair; an invalid reviewer
  response continues review without rerunning completed implementation/checks.
- [ ] Selected finite budgets, pins and command/spending authority still enforce.
- [ ] Reload at a continuation boundary preserves decisions and avoids duplicate
  side effects. Resume chooses a useful action instead of replaying exhaustion.
- [ ] Temporarily unavailable routes wait; a true missing prerequisite is stated
  accurately without inventing new authorization or another arbitrary stop cap.

Use small deterministic continuation cases and existing executor fixtures.
Follow T94's validation/cost policy; no new heavy end-to-end workflow by default.
