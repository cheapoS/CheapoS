# Complete the work without operator rescue

cheapoS should feel like working with agents that remember the task and finish
it. An unattended task succeeds when it reaches a trustworthy, reviewable result
within the operator's authorization. Displaying an understandable error and a
Resume button is not a successful recovery.

This is the development direction for the next iteration. The item-review and
final-review handoffs described below are implemented; the broader changes are milestones,
not claims about current behavior.

## What went wrong

We have repeatedly treated engine failures as operator decisions. The recent
review incident illustrates both layers: a contradictory tool schema provoked
invalid approvals, then Resume reopened the exhausted review state. Explaining
the failure and adding a reviewer-selection button still required the operator
to diagnose the engine and rescue work that was already implemented and checked.

Local recovery counters and scattered exception handlers have become accidental
task-completion policy. Worker, reviewer, planner and transport recovery need to
agree on what remains unfinished and what can happen next.

## Development contract

- Ordinary model, transport, formatting and non-progress failures belong to the
  engine. Preserve the work, choose a materially different next action, and
  continue automatically when it is authorized.
- A progress threshold triggers a change of strategy, not a task stop by itself.
  Do not add another arbitrary retry-count ceiling on top of the operator's
  chosen work and spending limits.
- Retain the objective, approved scope, conversation, current operation, edits,
  check evidence, unresolved findings and attempt history across handoffs and
  restarts. Another model should continue the job rather than rediscover it.
- Respect a provider's cooldown. Try another eligible route or wait for a useful
  availability check; repeatedly hitting the same endpoint is not recovery.
- Reuse checks only while their command, candidate and environment still match.
  Do not send the worker back through implementation when only review is left.
- A valid reviewer rejection goes to focused repair. Changing reviewers must not
  be a way to discard a real defect or hunt for approval.
- Ask the operator for a decision only when it cannot be made within the saved
  authority: essential scope information, credentials, command approval, changed
  spending/model policy, or final integration. Describe the actual decision.
- If no authorized strategy can proceed, state what was tried and the specific
  remaining prerequisite. The operator should never need a magic chat phrase.

Errors remain available as diagnostics. Chat should show useful progress such
as “The reviewer couldn't complete its decision; continuing review with …” or
“Waiting for an available authorized provider.” These updates describe actual
engine actions, not optimistic status text.

## One continuation decision, existing executors

Extend `cheapos/continuation_policy.py` into the common next-action decision for
planner, worker, reviewer and transport failures. Keep it deterministic; do not
add a paid model request just to decide whether to retry a known failure.

The decision consumes the saved operation and current evidence. It selects one
of: continue the current operation, repair malformed output, use another
authorized route, resume focused implementation, reuse/run the required check,
wait for availability, or request a necessary operator decision. Existing
executors keep ownership of file operations, command grants, accounting, model
dispatch and Git integration.

Persist the selected continuation before dispatch, with its candidate/operation
identity, attempted routes, evidence references, next eligible time when known,
and outcome. Restart must distinguish “selected but not dispatched” from
“dispatched with uncertain outcome.” A new model conversation does not reset
the task's cumulative usage or erase an unresolved finding.

Resume should invoke this decision from saved state. It must not blindly replay
an exhausted operation, manufacture a new task, or clear counters until the same
broken request happens to run again.

## Milestones, in order

1. **Finish the current reviewer recovery path.** Invalid decisions, repeated
   reads and missing decisions lead to another unused authorized independent
   reviewer after focused reassessment. Preserve the failed exchange and reuse
   valid checks. Resume on existing stalled items takes this same path. No new
   handoff-count cutoff; existing task limits and route eligibility still apply.
   Acceptance: a scripted reviewer fails, another finishes review, and no
   operator message, worker rerun, extra verification or synthetic approval is
   needed. A valid rejection still leads to repair.

2. **Unify continuation across phases.** Audit planning, implementation, item
   review and final review entry points and their exception handlers. Replace
   stop-by-counter paths with common continuation decisions. Keep genuine
   authority failures distinct from model failures. Acceptance: each recoverable
   failure has a demonstrated automatic next action; unsupported recovery ends
   in an explicit prerequisite, not “add a correction.”

3. **Make saved context sufficient to continue.** Build a shared continuation
   packet from durable task state: objective, scope, current candidate, finished
   work, exact remaining action, current checks and unresolved findings. Treat
   model summaries as advisory and bind evidence to the actual candidate.
   Acceptance: replacing a worker/reviewer or interrupting dispatch does not
   lose the current operation, repeat completed edits or hide a review finding.

4. **Make temporary unavailability a waiting state.** Carry connection/model
   cooldowns and next eligible checks into continuation. A queued task remains
   visibly alive and cancellable, resumes when a route is eligible, and does not
   flood providers while waiting. Acceptance: fake-clock cases cover cooldown,
   alternate provider, cancellation and restart without real sleeps or calls.

5. **Qualify completion, not error presentation.** Maintain a small deterministic
   set of complete continuation scenarios: invalid reviewer output, provider
   cooldown, malformed plan, worker stall, and restart between dispatch stages.
   Track successful completion without operator intervention, repeated calls,
   repeated checks, handoffs and total usage. Live trials remain explicit,
   measured and within the selected spending policy. Do not add expensive test
   fixtures without the repository's test-cost disclosure and approval.

## Review every recovery change against this question

Does this change let the task continue and finish without the operator doing the
engine's work? If it only adds error wording, another button or instructions to
type into Chat, the underlying recovery work is still incomplete.

## Implemented: continue final packet review

Final review now uses the same continuation policy as item review. Repeated
invalid decisions or unchanged context reads trigger another unused authorized
independent reviewer when automatic placement permits it. The failed exchange,
context references, selected route and cumulative failures survive restart.
Manually pinned reviewers stay pinned until the operator chooses another model.
No handoff renews task usage, command permission or spending authority.

Completed packet decisions are retained against the exact manifest, packet
evidence and operator direction. Resume reuses matching decisions and passing
checks, then continues the remaining packets and final synthesis. Changed
evidence must be reviewed again. Valid defects still require repair; missing or
invalid coverage never becomes approval. Readiness records the reviewer that
actually completed each packet and synthesis.

Candidate context reads page large requested ranges at 200 lines and retain
the existing path, candidate identity and character bounds. There is no separate
six-read stop. Exact repeated reads reuse their saved excerpt and trigger
reassessment or handoff when they stop adding evidence. Task limits and Pause
still apply. Small in-memory cases cover continuation, restart, pool exhaustion,
manual selection, context paging, cached coverage and unchanged authorization;
the existing Git final-review tests cover readiness and integration safeguards.

Approved runs also retain their captured execution and model defaults. Changing
the default local reviewer, coordinator or model pair for new tasks does not
invalidate a paused task's authorization on Resume. The current gateway identity
and connection revision are still checked; saved scope, commands and spending
authority cannot expand. Unapproved proposals still detect changed defaults
before approval. Regression cases exercise the actual Resume entry point after
restart using an in-memory task and retain checks, usage and authorization.

## Implemented: recover from a bad file edit

Worker text edits now retain the latest 16 completed edit receipts inside the
task record. These include the exact pre-edit bytes and file mode, but the
worker's context and browser task payload never receive the stored file bodies.
`read_edit_history` exposes receipt IDs and current-version status; `undo_edit`
restores only the selected file when that receipt is its latest unchanged edit.
Newer same-file changes, another item's work, a changed feature tip or a completed
interactive commit make an old receipt ineligible. Path restrictions, branch
write authority and the one-mutation-per-file-per-response rule also apply to
undo. Existing tasks get receipts for edits made after this upgrade; old edits
are not retroactively given undo authority.

A text edit that introduces invalid Python or JSON syntax into a valid existing
file is automatically restored before the worker continues. The tool returns
the actual current lines and explains which edit was rejected. New files being
written in chunks and files that already contain syntax errors remain editable.
Python edits also report added/removed qualified symbols, possible scope moves
and new duplicate definitions. These are evidence, not a ban on refactoring:
the worker can see that `Manager.run` became `helper.run`, or that a new test was
appended to a class without its intended fixture.

Repair packets group identical exception messages and label whether the latest
check predates the current patch. Full original check output stays retained.
After repeated failed verification, automatic placement requests an eligible
worker handoff with this evidence; fixed worker choices remain fixed. The old
six-failure stop and instruction to rewrite the whole implementation are gone.
Explicit checks and checkpoint verification use the same repair feedback.
All approved check commands, remaining work/spending limits, provider eligibility
and independent review requirements still apply. Undo is never a passing check.

Validation uses tiny deterministic file and controller cases, including a bad
edit followed by repair, a passing check and independent approval. No live model
calls or new multi-item Git qualification runs are required for these cases.

## Implemented: continue an unfinished worker recovery

A recovering worker can inspect missing file context. Its guidance now matches
the offered read/search tools instead of telling it to ask the operator when a
snapshot is incomplete. An omitted `read_file.end_line` reads up to 200 lines
from the requested start, including starts past line 200. Existing path, size
and explicit-range bounds remain in force.

A text-only response during recovery stays in the worker loop for the next
action. It no longer returns a still-running item to the branch controller and
turns useful saved context into an unknown-stop banner. Existing non-progress
handling, task limits, command permissions, independent review and operator
Pause still apply. Deterministic cases exercise text followed by a late-file
read, edit and checkpoint dispatch, plus stopping before another model call.

## Implemented: smaller review inventories and precise allowance stops

Interactive and item reviewers receive a bounded preview of large `list_files`
results, with a task-local reference for retrieving the complete listing.
Saved reviews get the same treatment when resumed. Source reads, diffs,
criteria, findings and check evidence remain unchanged; directory discovery
does not need to consume the full prompt allowance on every subsequent turn.

The request reservation still checks the existing authorized allowance before
dispatch. If a request cannot fit, its structured budget reason survives the
worker/branch wrappers and appears as a work-limit stop. Older unknown stops
can recover that explanation from the exact associated failed request. A local
budget refusal is not recorded as an invalid model response, and cannot grant
more tokens or spending. A small deterministic case resumes a saved review,
fits its listing into the remaining allowance, and reaches independent approval
without repeating implementation or checks.

## Implemented: resume Uncapped Interactive work

Switching an Interactive task to Uncapped removes the old exhausted-recovery
admission block. Resume and short chat continuations keep the original request,
conversation, usage, findings and coordinator attempt history. A conditional UI
change request remains implementation even before the first edit; an old
answer-only step returns to the worker's ordinary tools. Repeated inspection
after unavailable coordinator advice changes strategy within the saved authority
instead of imposing another work cap. Automatic placement can request another
eligible worker; fixed model choices remain fixed. Command permissions, spending
limits, independent review and final commit approval are unchanged.

Coordinator packets prioritize paths in saved tool metadata as well as current
runtime observations, so restart does not drop an inspected file merely because
it falls beyond the first 100 indexed paths. Paths must still exist in the
validated workspace index; current excerpts are read again before advice is used.
Stopped Uncapped Interactive chats show Resume without requiring a new prompt.

Validation includes an in-memory continuation through repeated inspection, edit,
verification and independent approval, plus permission gates and retained usage.
These cases use no model calls, Git workflows or real-time waits.

## Implemented: start an approved snapshot after another task merges

When the base branch advances while a prepared task waits for approval, startup
continues from the same inspected private snapshot and pinned base commit.
It does not adopt the newer files, replan, or change the approved scope, commands,
models or limits. Startup records that it is using the approved snapshot. Final
integration still requires the existing target update, verification and review.

Rewritten/deleted base history, changed private snapshots, branch ownership
conflicts and changed command scope still block startup. Known repository failures
retain their specific explanation; unexpected startup errors retain a diagnostic
reference and server traceback, without attributing setup to an old planner call.
Validation uses small deterministic startup cases and the existing Git/HTTP
fixtures for sibling merges, immutable copies, authorization and integration.
