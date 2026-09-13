# T33 — Sequential execution with recovery and shared limits

**Depends on:** T32. **Size:** L. **Result:** cheapoS completes the accepted items sequentially, automatically moving from a verified commit to the next task.

Read [BRANCH_RUNS.md](../../BRANCH_RUNS.md) and AGENTS.md first. This is the scheduler/controller card. T35 supplies plan generation/UI; use structured fixtures now.

## Read first

`Engine.start/_run/_run_until_pause/initial_messages`, `Runtime.guard`, `progress.py`, `work_policy.py`, routing/cooldown recovery, provider usage reservations, project context, and T28–T32 contracts.

## Implementation

1. Add a controller-owned loop over dependency-ready items in stable accepted order. Maintain one active worker item and existing supported runtime concurrency. Do not create a visible new chat per item or recursively call public `Engine.start()` in a way that resets budgets, duplicates user turns, or conflicts with active-runtime checks.
2. Supply each item with its own instructions/criteria, the project brief, relevant completed-item outcomes, and current files/evidence. Keep the accepted plan durable outside the model context window. Avoid replaying the entire earlier conversation at every item; preserve constraints and unfinished questions when compacting.
3. Move through worker → required checks → independent review → T32 commit (or reviewed no-change outcome) → next item. A checkpoint can approve an intermediate patch but does not finish the item unless its acceptance criteria are satisfied. Do not allow a model to skip dependencies, drop tasks, expand scope, or declare the whole run complete.
4. Feed failed assertions and REQUEST_CHANGES back into normal bounded repair. Reuse existing malformed-tool, small-edit, read-loop, free-model rotation, and cooldown policies rather than nesting another unbounded retry layer. Track which failure/repair was already attempted; new item boundaries reset only item-local recovery, not run limits.
5. Add one cumulative run ledger for reserved/accounted cost, worker/reviewer usage, active working seconds, and explicit outer request/action limits. Planning, probes, handoffs, final review, and uncertain requests consume the same authorized resources where applicable. Item starts, user Resume, and server restarts must not reset them. Keep per-item progress/checkpoint intervals separate from the outer hard limits. Define a validated run-limit schema without silently widening manual task settings; existing per-chat caps (such as 20 iterations) cannot simply become a total cap that makes a 50-item accepted plan impossible. Propose finite overall allowances from the plan, show them before authorization, and flag a budget that cannot cover even the mandatory review stages.
6. Account active time with monotonic segments persisted at meaningful boundaries and bounded intervals during long requests/checks. On crash, retain a conservative consumed reservation for the unclosed segment so repeated restarts cannot manufacture time. Exclude confirmed paused/offline/operator-wait intervals; count authorized route waiting. Document the exact recovery accounting rule and clock-change behavior.
7. Emit structured start/check/review/commit/next-item/pause events with run/item/sequence identity for T36. A successful commit immediately schedules the next item; do not emit the ordinary “what next?” chat close between items.
8. When all items are terminal successful outcomes, transition to `finalizing`. T37 owns final readiness; until available, expose “Implementation complete; final verification pending” and do not claim `ready_for_merge`. Hard limits/missing setup/unsupported actions explain the exact blocker and preserve all work.

## Acceptance and validation

Run a deterministic three-item plan through real temporary edits/tests/commits with one failed test and one reviewer revision. After initial authority/grants, no per-item human approval is requested. Verify ordering, context passed to each item, and no empty “success” for unfinished criteria.

Exercise cost/time/turn exhaustion, free-route cooldown, repeated malformed calls, and missing dependencies. The run must stop at the actual outer bound without losing work or automatically escalating to paid/local execution. Existing single-task loops remain compatible. No new background scheduling service or parallel workers.

## Completion record

Status: Todo

Behavior delivered:

Acceptance evidence:

Commands and results:

Browser scenarios and results: T36 owns the visible flow; controller integration is required here.

Remaining limitations:
