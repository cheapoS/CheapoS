# Complete the work without operator rescue

cheapoS should feel like working with agents that remember the task and finish
it. An unattended task succeeds when it reaches a trustworthy, reviewable result
within the operator's authorization. Displaying an understandable error and a
Resume button is not a successful recovery.

This is the development direction for the next iteration. The item-review and
final-review handoffs described below are implemented; the broader changes are milestones,
not claims about current behavior.

## Implemented: merge around unrelated local drafts

Unattended branch integration compares destination edits with the exact incoming
file changes. Unrelated staged, unstaged and untracked work can remain in place
through preview, explicit merge approval and interrupted-merge recovery. It is
neither committed into the task nor stashed or discarded. A newer target still
goes through the existing isolated update, conflict repair and independent review.

Edits on affected paths, rename endpoints, file/directory collisions and ignored
files that would be overwritten remain protected. These checks repeat at the
actual merge and recovery; branch ownership, destination identity and approval
checks still apply. Interactive direct commits retain their existing safeguards.
Resolving overlapping **uncommitted** drafts with agents is not implemented by
this change: it needs a captured local/index snapshot, review of the combined
result and conditional application that preserves edits made after capture.
The existing agent conflict workflow resolves committed branch changes only.

## Implemented: discussion is separate from execution

An opening greeting in remote Interactive chat uses a small text-only request.
Automatic selection favors successful observed response times on the authorized
connection, without a synthetic coding-tool probe or repository context. This
does not qualify that model for tools: subsequent implementation still uses the
ordinary worker selection and verification flow. Explicit model pins, access
policy, provider pacing, cooldowns and spending limits continue to apply. This
avoids unnecessary setup; it does not guarantee a remote provider's latency.

Existing chats accept questions and discussion while work is running, paused,
awaiting review, or merged. Explicit questions, explanations, examples and social
replies use a read-only conversation turn; ambiguous or implementation requests
keep the existing execution path. Mixed questions and requested edits remain
worker instructions. Code examples are allowed in chat and do not count as edits.

Replies use the saved task context and normal model connection, spending, token
accounting and read-only workspace tools. They do not use the local coordinator.
During work they run at model-operation boundaries, or while waiting for command
approval, with an immediate saved-message receipt. An in-flight request or check
finishes first. The work's requirements, review, check evidence, pause reason and
recovery history remain intact. Discussion is included as discussion in later
worker context; it is not silently added to the acceptance criteria.

Work-turn/request ceilings do not prevent answering a question or count chat
replies as implementation progress. Monetary and per-request limits still apply,
and all usage remains visible. A chat reply is not code authorship or independent
review evidence. Sending a message no longer implicitly approves an uncapped
takeover. Tests, review, command consent and final integration approval remain
required on their existing work paths.

The same chat remains open for discussion after integration; starting a new
authorized job after a merged unattended run still uses the existing new-job
flow. Restarted incomplete replies are labeled interrupted, never left spinning
or replayed as work. Deterministic tests cover questions during review, paused
work, example snippets, denied mutation tools, accounting and spending refusal.

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

## Planned: operator-owned limits

The next limits iteration follows [Operator-owned limits and automatic
recovery](docs/development/operator-limits-and-recovery.md). Cumulative work
budgets should be explicit user settings with visible scope and provenance.
Internal thresholds should choose another useful strategy within that authority.
Existing saved budgets remain intact; spending, permissions, model pins and
independent review still apply. This is the implementation design, not a claim
that every existing hardcoded limit has already been removed.

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

## Implemented: reuse approved unittest commands

When an unattended worker requests an explicit unittest check with the same
interpreter and selectors but different verbosity or an omitted Python `-B`,
the controller uses the original approved argument list. This also works for
an exact-approved file path such as `examples/penny-pinner/test_pinner.py`,
without granting a broader project test profile. The requested and executed
commands remain visible in the event record. Passing evidence is bound to the
executed command and can be reused before independent review.

Selection changes, discovery, filters, unfamiliar options and other interpreters
do not receive this substitution. The original command must still have a current
grant with matching workspace, runner and configuration. Revocation and restart
do not gain new authority from a saved plan. Small deterministic cases cover
execution, evidence reuse, independent review and stale-grant rejection without
model calls, Git workflows or real-time waits.

## Implemented: scope upstream access failures and explain route waits

A recognized upstream access refusal blocks that provider, while automatic
placement continues with other authorized providers through the same gateway.
An ambiguous authentication failure still blocks the gateway connection. Cached
access failures are not treated as quota resets: if every otherwise eligible
route requires access repair, the task names that prerequisite instead of
cycling through local availability checks indefinitely. Provider failures do
not spend model-quality handoffs or discard checks, context or usage.

Waiting views say that no model request is running, show the next availability
check, and retain elapsed waiting time across consecutive discovery rounds.
Planning uses the same waiting state. Checks use synthetic responses and clocks;
there are no added live requests, real sleeps or Git workflow fixtures.

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

Final requirements packets contain the accepted task criteria and instructions.
Completed repair notes and earlier item outcomes remain hash-bound historical
evidence, retrievable through `read_context_evidence`; they do not create new
requirements to repair the controller's own history. Unchanged repair notes stay
historical after conflict resolution reauthorizes a run. Explicitly revised
operator instructions and integration requirements remain in current coverage.
Reviewers still inspect the complete current diff and final checks, and genuine
defects against the accepted criteria still require repair. Previously issued
readiness receipts retain their original manifest format for validation.

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

## Implemented: large branch items are reviewed in pages

A large accumulated patch, including incoming target changes during conflict
resolution, is not an exhausted work allowance. Branch items retain the full
patch and page oversized review evidence through the existing independent
packet reviewer. Each byte of the packet receives recorded coverage before the
normal item decision verifies every acceptance criterion. Full evidence and
packet feedback remain available by reference; saved approvals cover only their
exact candidate and evidence. Completed pages survive Resume, and invalid packet
responses use the authorized reviewer handoff path.

Concrete defects still return to focused repair. Required checks, candidate
validation, independent review and spending limits still apply; paging does not
approve work or increase authority. The legacy compact-review size guard remains
on the separate Interactive review path.

## Implemented: inspect files accepted into the task copy

Text inspection and existing-file edits share the snapshot's 2 MB file limit.
A file accepted into the task copy must not disappear from search or fail an
outline just because it exceeds the former 256 KB text-tool limit. Reads return
at most 20,000 characters with line/column continuation, including long lines;
outlines return at most 100 symbols with a continuation line. Full-file hashes
still bind versioned edits to the inspected file. New-file generation and small
edit limits remain separate and unchanged.

Small deterministic cases cover large Python and JavaScript files, paged
inspection, search, a versioned edit and undo, plus path/binary restrictions.
They require no models, Git workflows or real-time waits.

## Implemented: reassess new recovery evidence and prepare clean merge files

Optional coordinator help now follows the current patch, check result and review
evidence within an item. A later failure after code changes can receive fresh
help. Unchanged reads, repeated checks, Resume, elapsed time and usage do not
renew the same consultation; previous attempts and accounting remain saved.
Coordinator packets retain the failure end of test output instead of only the
initial passing tests. Unattended UI describes automatic assistance accurately.

Automatic branch-worker recovery may try further unused authorized workers after
the old two-handoff threshold. It retains failed-model exclusions, task limits,
spending and command authority, check evidence and independent review.

Before a conflict worker continues, the controller applies captured Git-combined
nonconflicting files that still match their original task version. Existing edits
and textual conflicts remain untouched. This preparation is restart-safe and
does not approve or commit the result; verification and review still follow.

## Implemented: review integration changes against the captured target

Conflict-resolution item review compares the complete candidate with the frozen
incoming target. Unchanged imported target code no longer fills review pages.
A second diff against Git's captured suggested merge exposes dropped task work,
missing incoming changes and unexpected edits, including outside conflict paths.
Original task requirements accompany both comparisons, and every review page
identifies their bases. Reviewers can inspect current source, frozen merge
versions and the retained full item patch when assessing interactions.

The candidate, required checks and commit receipt still bind the complete patch.
Independent approval and all acceptance criteria remain required. An already
started legacy packet keeps its exact contents and completed page approvals on
Resume; new candidates use the smaller comparison. Source checkout, index and
branch refs remain untouched while constructing the review.

Coverage uses one small Git comparison fixture plus in-memory packet and
continuation cases; it does not add another full agent workflow or live model run.

Integration retries carry an existing dispatch only when the candidate, requested
target, target ref and task-copy identity still match. A reviewed branch paused
because its target advanced returns to the update path instead of repeating final
review against the old branch. Unfinished resolutions keep their existing worker
assignment. In-memory cases cover both new updates and restored stale dispatches;
checks, spending authority and independent review remain unchanged.


## Implemented: retain requirement identity across repair rounds

Final-review findings may name an earlier repair item's criterion. Worker and
reviewer preparation resolve that reference to the saved original requirements
without discarding the finding ID, counterevidence or independent review. The
entire mapped scope must belong to the current authorized repair, including
duplicate requirement text.

A malformed saved repair is a local controller error, not evidence against the
selected model. Existing runs can reclassify the specific earlier reference
failure only when their saved recovery event matches an undispatched request.
Attempts and usage remain recorded; actual provider failures, access restrictions
and probe rejections remain in force. In-memory continuation cases cover worker
preparation through independent approval and a preserved reviewer rejection.

## Implemented: recover from rejected edits without replaying them

Syntax rollbacks retain the valid file and now count as rejected work. They do
not clear failed-edit or repeated-read evidence. An identical rejected edit on
the same file version is not executed again, including after restart. Repeated
syntax failures consult the optional coordinator, then use an authorized worker
handoff when help is unavailable or already exhausted. Pinned workers keep their
selection and can use exact-text edits to escape a failed line-edit strategy.
Whitespace/comment-only Python changes do not renew the same repair attempt.

Missing or ambiguous exact-text replacements also retain structured rejection
evidence across restart. Replaying an identical replacement on the same file
version returns current numbered lines without executing the failed edit again.
Repeated mismatches change strategy through the same coordinator/handoff path
and supply current evidence for version-bound line edits. Exact-text and line
editing remain available. An accepted edit clears that file's mismatch
state; verification and independent review still determine completion.

File mutations validate their declared required fields before clearing argument
recovery. Valid JSON with a missing/empty path or missing/wrong-type content is
still a format failure, not a successful correction. These failures use the
existing focused repair and authorized handoff path; empty file content remains
valid. Rejected historical calls become controller diagnostic notes with exact
task-local evidence references, rather than synthetic empty assistant calls.
Successful sibling calls and uncertain interrupted outcomes retain their evidence.
Legacy sanitized calls are also removed from tool-call examples on continuation.

Uncapped and measurement runs still inspect progress at checkpoint intervals;
stalls change strategy rather than enforcing a work ceiling. The legacy two-model
handoff ceiling no longer stops uncapped Interactive work. Spending, command
grants, file versions and independent review remain enforced. Source-text
arguments in XML fallback calls preserve literal whitespace and string values.

Small file/in-memory cases cover duplicate rejection after restart, coordinator
guidance through verification and independent approval, automatic handoff,
pinned choices and pending permission gates. See the
[read-only limits and recovery audit brief](docs/development/limits-recovery-audit.md)
for the remaining cross-phase audit; these patches are not a claim that every
hidden limit or stalled operation has been addressed.

## Implemented: retain progress and shorten repeated failure context

Progress tracking no longer stops accepting new patch/check/review states or
inspected file versions after 1,000 entries. Its exact saved index continues to
recognize old states after restart, so cycling back to earlier work does not
earn progress. Documentation and comment edits remain valid changes; this is
not a global semantic filter or a new work allowance.

Worker requests fold adjacent duplicate rejected-edit exchanges into the first
and latest exchange plus a summary with retrievable task-local references.
The saved conversation, attempts and usage remain intact. Every distinct result,
file version, assistant finding, intervening instruction and incomplete tool
exchange stays in the request. Only known syntax rollbacks and unexecuted invalid
ranges or text matches qualify; ambiguous tool errors and successful edits do not. Reviewer
evidence is unchanged. Request metrics record omitted exchanges and payload
bytes before/after this projection; token reservations use the resulting request.

Small in-memory cases cover more than 1,000 states and file versions, legacy
state migration, restart, exact evidence retrieval, authority preservation and
the worker/reviewer request boundary. Existing deterministic recovery cases
still cover repair through verification and independent approval.

## Implemented: coordinator advice for required new files

Recovery packets distinguish existing file evidence from paths explicitly named
in the active approved item (or operator instructions for Interactive work).
The optional coordinator can recommend creating a required new file through
normal worker tools; it cannot request a context read from a missing file or
expand execution authority. Workspace path restrictions, read-only requests,
checks and independent review still apply. Matching saved advice rejected only
by the old existing-file rule can be revalidated without another model request.

A local coordinator connection failure is shown as unavailable, separately from
a rejected reply. Worker recovery continues within the saved authority. Local
assistance remains on demand, with no background inference. Small contract and
dispatch cases plus the existing unattended recovery workflow verify these
paths without live model calls or a new heavy test fixture.

## Implemented: keep optional checks from interrupting unattended work

When a worker invents an extra command outside its saved grants and the current
item has authorized checks available, the controller returns those checks to
the worker without executing the extra command or opening a permission prompt.
The worker can add assertions to test files covered by an approved runner and
submit the item for independent review. Repeated extra-command requests trigger
the existing worker recovery path; changing the extra arguments does not reset
that signal. Attempt history survives task reloads.

The rejected command is never reported as passed or silently replaced with a
different test. Required checks still run before review. Revoked or stale consent
for a required command still needs operator authority, and an essential check
that cannot be performed within saved scope can be reported as a specific
blocker. Explicitly granted extra commands and Interactive checks retain their
existing behavior. Deterministic dispatch tests cover these distinctions without
starting commands, models, Git workflows or real-time waits.

## Implemented: recover from unmet edit prerequisites

An edit blocked by a missing defect reproduction now returns the saved finding,
the current item's planned checks, and current lines from an existing test file
when its selector can be resolved. The worker can add a discoverable regression
to that file and run the normal check tool. Reviewer snippets remain evidence,
not command consent. Passing or stale checks do not unlock implementation edits;
a disproved finding still needs counterevidence and independent review.

Repeated blocked implementation edits, attempts to create an existing file, and
oversized edits trigger the existing coordinator/authorized worker recovery path.
Attempts persist across task reloads and are scoped to the work item, disputed
candidate and worker. Trying another implementation path cannot reset a missing
reproduction. Existing files, edit bounds, command grants and review findings
remain intact. Small file/in-memory cases cover reproduction, retained tests,
repair and independent approval without operator rescue or live inference.
Oversized-edit feedback includes measured old/new line counts, UTF-8 byte counts
and the particular limits exceeded, so workers can choose coherent smaller edits
without guessing which bound rejected a payload. These diagnostics contain sizes,
not an extra copy of the rejected source text.

## Implemented: coherent edits without artificial chunk limits

Accept a complete valid replacement within file resource ceilings. Do not reject
it because it exceeds a model-quality heuristic such as 80 lines or 3,000 bytes.
All normal edit tools stay available. Smaller edits are temporary recovery advice
after actual malformed arguments or truncated output, rather than a permanent
mode inherited by subsequent workers. Successful edits end malformed-argument
guidance; complete responses end truncation guidance. Worker, connection, item,
baseline and user-request changes expire stale guidance while preserving attempt
history and usage. Resume alone does not erase an unresolved attempt.

The existing 256,000-byte new-file and 2,000,000-byte edited-file resource ceilings
remain. Version checks, workspace boundaries, existing-file protection, syntax
rollback, defect reproduction, command authority, verification and independent
review are unchanged. Small deterministic cases demonstrate a complete rewrite
through verification and independent approval without artificial chunk retries.

## Implemented: final-review path guidance and replacement-route recovery

Final reviewers use exact repository-relative paths from the change manifest.
An unavailable read retains its exact requested path and offers matching manifest
paths as hints; it never silently redirects the read or establishes approval.
Diff line counts do not create new requirements. Previously disproved findings
need current candidate evidence before being reopened.

Reviewer identity recovery keeps trying authorized replacements after ordinary
recoverable route failures, including model request rejections. It rechecks
provider cooldowns between replacements so one provider's remaining models are
not dispatched from a stale candidate list. Shared request errors, access,
operator-selected models, spending limits and reviewer independence still apply.
Known HTTP 400/422 stops retain a safe typed explanation without exposing provider
bodies. Small simulated cases cover corrected paths and final approval after a
replacement request fails, without worker edits, repeated checks or operator rescue.

An authorized reviewer handoff now takes precedence over an older identity
recovery selection. The replacement still passes current eligibility and response
identity checks; failed attempts, provider cooldowns, explicit model choices and
access failures remain enforced. Saved handoffs continue after restart without
first dispatching unrelated recovery candidates.

Final review accepts the exact `functions.` namespace alias of an offered tool.
It still validates the decision, exact candidate and coverage, concrete defects
and reviewer independence. Other tool names and malformed coverage are rejected.
Chunk-completion events identify their position and total instead of appearing
to announce completion of the entire final review. Small in-memory cases cover
handoff through approval, restart reuse, retained rejection findings and aliases.

Replacement reviewers also use their own catalog provider metadata. A stale
provider label must not apply another provider's pacing or misclassify a known
upstream access refusal as a shared connection failure. The known refusal skips
that provider and continues authorized independent review; ambiguous gateway
credential failures still require attention. A deterministic six-chunk replay
covers timeout, upstream refusal, replacement approval and reuse of saved reviews
without repeating worker edits or checks.

## Implemented: final repairs follow the authorized work budget

Final-review corrections no longer stop after three lifetime amendments. Each
new correction stays bound to the original requirements, verification commands
and saved authorization. Initial proposal-size bounds do not cap the accumulated
repair history. The runtime continues enforcing the operator's work and spending
limits; this does not renew counters, alter model placement or approve a claim.

The worker verifies a finding, preserves counterevidence when it is disproved,
and submits it through independent review. Existing disagreement stops use the
ordinary Resume action instead of sending the operator to Activity to adjudicate
model claims. Focused in-memory cases cover a fourth repair through independent
approval, saved history, unchanged authority and proposal bounds.

## Implemented: checks retain their working directory

A component check carries both its executable command and its task-relative
`directory`. For example, `{"command":"npm run build","directory":"cloudflare"}`
runs in that component for worker verification, item checkpoints and final review.
The planner captures the directory from project evidence; acceptance text alone
cannot change execution. Existing string checks continue to mean repository root.
The proposal and verification editors display scoped checks as
`[cloudflare] npm run build` and preserve that directory through editing.

Directory is part of command consent, verification identity and evidence reuse.
Identical commands in different folders are separate checks. Paths outside the
task copy, Git internals and escaping symlinks are rejected. Exact component
consent cannot become a root project-test grant. Setup commands remain separate
from verification, and missing component setup returns to an authorized worker.
A check in the wrong directory is a contract problem, not a reason to create
out-of-scope wrapper files or weaken the review criteria.

Trusted check amendments may update the current item, final checks and explicitly
named pending sibling items together. They retain the previous authorization and
check history, invalidate affected readiness, and keep usage and file scope.
Committed or already-started siblings cannot be rewritten by this amendment.

## Implemented: give planners the contract before correction

Planning starts with a short checklist, the two available tools, a canonical
proposal format and a clearly labeled structural example. The advertised schema
requires the complete item and plan fields; the parser still accepts supported
legacy response forms without another model request. Commands retain their
working directory and the planner must copy the operator's displayed limits.

Each request adds one fresh index of recent inspections, failed paths and partial
read continuation coordinates. Full evidence and paired tool replies remain in
history. This reminder does not accumulate in saved messages, cap inspection or
grant execution authority. Resumed sessions receive the current opening contract
without resetting recovery attempts, evidence, usage or pending proposal requests.

Routine format and inspection corrections remain in Technical logs, with their
attempt numbers and diagnostics. Chat shows the automatic planner handoff and
keeps useful findings, actual failures and operator decisions visible. Small
deterministic replays cover malformed proposals and failed inspections through
automatic handoff to a valid proposal, including restart with retained history.
