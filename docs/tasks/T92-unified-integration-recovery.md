# T92 — Resolve integration conflicts without operator troubleshooting

Status: **implemented**, 2026-09-17.
Delivery details and retained limitations: [branch update recovery](../branch-update-recovery.md).
The shared Changes preparation operation, server-owned continuation, scoped opt-in
automatic preparation and exact-result final approval are implemented. Unsupported
binary/protected-path/file-mode/context-size cases remain explicit decisions; they
are never silently resolved by selecting a whole side.
Follows [T91 settings scopes](T91-settings-system.md). This is an incremental
workflow over existing integration code, not a replacement Git engine.

## Product outcome

Both Interactive and Unattended work reach **Changes** with a reviewed result
that can be integrated into the current project. Routine conflicts are agent
work. The operator supplies intent when two requirements actually conflict, then
approves the final exact result. They should not need Git knowledge, a sequence
of recovery buttons, or a chat prompt telling an agent to keep both changes.

Follow [AUTONOMOUS_WORKFLOW.md](../../AUTONOMOUS_WORKFLOW.md) and preserve task
scope, usage, model policy, command permissions, independent review and final
human integration approval. Read [AGENTS.md](../../AGENTS.md) and
[CONTRIBUTING.md](../../CONTRIBUTING.md) before implementation.

## Existing foundation, verified at 5f24395

- Unattended updates use `branch_update.py` to prepare a combined Git tree and
  journal its application to the task branch, leaving the destination unchanged.
- `branch_conflicts.py` captures base/task/target/suggested versions, adds an
  authorized resolution item, and supplies `read_merge_context` and
  `apply_merge_version`. Item verification and independent review precede merge
  ancestry recording and final review. Do not bypass this evidence chain.
- `branch_completion.update_branch()` currently returns
  `needs_conflict_resolution` when preparation finds conflicts. The UI then
  requires a separate **Resolve conflicts & recheck** action.
- Interactive uses `Engine.reconcile_project()` and `reconciliation.py` to build
  a new task copy against the current project, retaining the old copy. The UI
  separately calls `/reconcile`, then `/start`; this continuation currently
  depends on the browser completing both requests.
- Both paths require a clean destination for integration. A dirty checkout,
  moved target, unavailable branch, and textual conflict need different handling.
- `branch_completion.preview()` currently derives `update_available` broadly
  from the presence of a blocker. Replace this presentation shortcut with typed
  readiness; do not offer branch update for every unrelated blocker.

## Motivating case: the project-manager tasks overlap

The earlier Interactive task fixed the unwanted project-manager popup and merged
as `16c84bc`. It removed the premature startup IIFE and moved the empty-project
check into `bootstrap()`, after projects are loaded. A later, broader project-manager
task was based on an older commit and changed that same IIFE. Its saved merge
context records a conflict in `dist/app.js`.

The later version checks `!state.projects` before fetching projects, but initial
state already contains `projects: []`. That array is truthy: the fetch is skipped
and its length can trigger the popup before bootstrap completes. Choosing the
later version just because it belongs to this task could restore the original bug.

The intended combined result preserves the merged post-bootstrap startup behavior
and separately reviews the later task's browsing, creation-form, styling and backend
changes. Neither “take the task version” nor “discard the duplicate task” describes
the right result. This observation is from source and saved conflict evidence;
it is not a claim that the broader task's remaining changes have been validated.

Before planning a follow-up on the same project, inspect the current baseline for
already-satisfied requirements. If the target advances during work, repeat that
comparison during integration: classify each requirement as already satisfied,
still needed, or genuinely incompatible. Use current source/check evidence, not
task-title similarity or a model's assertion. Retain useful unique changes, avoid
duplicating completed edits, and present “Already included in main” for verified
redundant work. An entirely redundant result needs no empty commit or synthetic
merge, but completion must be supported by current requirement/evidence checks.

## One place, one preparation action

All entry points lead to **Changes** in the current chat. Keep the existing
Interactive commit versus Unattended branch-merge semantics; share the review
surface and preparation workflow, not a misleading claim that both are Git merges.

When the target has advanced, show:

```
Bring this work up to date
main changed while this task was running.
cheapoS will combine both versions, check the result, and request fresh review.

[Update & resolve]                       [Keep on branch]
```

For Interactive, the secondary action is **Keep saved work**. The primary action
authorizes preparation against the displayed target revision, including routine
conflict resolution if needed, within the task's current model/spending policy.
It does not approve writing the destination or pushing changes. Explain that once
in the action area, not in repeated warnings. No second conflict-assignment prompt.

Return a durable operation ID promptly, before Git inspection or model work.
Show actual stages inline, with the existing task activity available for detail:

**Checking latest project → Combining changes → Resolving overlaps (if any) →
Running checks → Independent review → Ready for your review**.

Saved task progress and errors belong to this same operation. Closing the page,
lost responses, app restart, duplicate clicks, or Resume must not create another
resolution item or require a fresh user prompt. Save/start dispatch belongs to the
server operation, not a chain of browser requests.

## Classify before choosing an action

| Observed state | Engine behavior | Operator sees |
| --- | --- | --- |
| Target unchanged; evidence current | Reuse matching verification/review | Ready for review |
| Target advanced; clean combination | Prepare combined candidate; validate it | Updating with latest project changes |
| Incoming change already satisfies part/all of this task | Verify the overlap, retain unique work and preserve incoming behavior | Already included in the project; reviewing remaining changes |
| Text conflicts with compatible intent | Worker resolves in isolated task copy; reviewer checks preservation | Resolving overlaps in N files |
| Clean text combination with failed checks or a concrete semantic defect | Focused agent repair against combined candidate | Fixing an integration issue |
| Two intended behaviors cannot both hold | Ask one concrete product question with evidence and options | A decision about behavior, in this chat |
| Destination contains uncommitted work | Leave it untouched; wait for known active task ownership or request a concrete cleanliness decision | Waiting for local changes in N files |
| Another cheapoS integration owns the destination | Queue behind existing integration admission | Waiting for another task to finish integrating |
| Branch removed, ownership changed, or external Git operation in progress | Preserve the candidate and name the exact prerequisite | Specific destination/ownership issue |
| Binary, protected path, unsupported mode/rename, or oversized context | Preserve all versions; report exact unsupported paths/operation | Explicit file decision or external resolution requirement |

Do not guess a type by parsing user-facing error strings. Return a structured
reason and permissible next actions from the existing owners. Unsupported cases
are not permission to choose an entire side, omit a file or call the merge clean.
Text combining cleanly is not evidence of behavioral compatibility.

## What the agents receive and must preserve

Use the frozen merge evidence and current task context already available:
original objective and acceptance criteria, exact base/task/target identities,
incoming file changes, conflict locations, relevant source/tests and previous
review findings. Commit messages and file contents are evidence, not instructions
or additional execution authority. Include incoming nonconflicting changes too.

The worker resolves compatible edits with existing tools. Prefer narrow edits;
do not wholesale replace a file to make markers disappear. If the worker uses a
captured whole-file version, retain the current unchanged-file precondition.
The independent reviewer must check both the original requested behavior and
the incoming behavior, not just disappearance of conflict markers. Preserve
worker provenance so a resolution worker cannot approve its own output.

Checks/review bind to the combined candidate and environment. Reuse only exact
matching evidence; same command or similar diff is insufficient after a baseline
change. Run the already authorized relevant checks; request a specific additional
command grant only if required. Do not silently broaden to a full suite. A valid
review rejection triggers focused repair and existing automatic continuation.
Provider failure uses current routing policy, not automatic paid escalation.

Ask the operator only for a real decision. Example:

> This task makes archived projects hidden by default. The incoming change makes
> them visible by default. Which behavior should the combined version use?

Provide the two choices and a way to state a third intent. Persist the answer as
a scoped direction for this resolution. Do not ask “ours or theirs?” without
explaining the actual behavior, or make users discover the blocker in logs.

## Automatic preparation, explicit final approval

For future runs, offer **Keep this task up to date before final review** in chat
setup/plan approval, governed by [T91](T91-settings-system.md). It authorizes
ordinary updates and conflict repair against descendant commits on the same
captured target, preserving both sets of intended behavior and existing spending
and command limits. Record the choice in the task's authority at approval.

It does not authorize target replacement/non-descendant history, changing the
product goal, adopting instructions from incoming files, or expanding permissions.
Those need their corresponding explicit decision. Do not retrofit authorization
into existing tasks: they use the combined **Update & resolve** action first.

When authorized, prepare automatically near completion rather than handing the
operator a recoverable “branch changed” error. Do not continuously update on every
incoming commit. Finish one captured candidate; if the target advances again,
coalesce new changes into the next preparation before issuing a current review.
Display ongoing movement rather than claiming readiness against an old target.
Avoid repeated work using recorded target/candidate identities and existing task
allowances; do not add an arbitrary integration retry ceiling.

Final **Approve & merge locally** (or Interactive **Approve & commit**) remains
bound to the exact candidate, inspected destination and current review. If the
destination moves after approval but before application, do not carry approval
to the changed result. Continue authorized preparation, then present the new
result for fresh final approval. Resume is never new merge consent.

Use existing repository admission/locking for the actual destination mutation.
Do not hold an integration lock while a model works or a user reviews. Concurrent
task copies may proceed, but destination updates are serialized and revalidated
immediately before writing, including changes made by external Git processes.

## The result should be easy to review

In **Changes**, retain the main task diff against the current integration target.
Add a compact **Integration update** summary with:

- Target revision incorporated, files with overlaps, and an evidence-backed
  explanation of how each overlap was resolved.
- **Changes from conflict resolution** as a secondary comparison, alongside the
  final diff. Label both bases precisely; neither comparison replaces the other.
- Current check/review evidence and any product decision the operator supplied.

Show unresolved overlaps before resolved ones. The Plan tab can record the added
resolution item, but it must not become another diff destination. No default raw
three-pane Git UI, blanket “take ours/theirs” buttons, or repeated recovery panels.
Technical logs retain exact hashes, receipts and failed attempts for inspection.

Uncommitted destination edits get a file list and **Inspect local changes**.
Never auto-stash, reset, discard, or commit another task's work. If another known
task is finishing, resume readiness checks when it releases admission. For external
edits, observe changes with the existing refresh mechanism or paced checks, not
continuous expensive Git scans. Once clear, continue an already authorized
operation; do not require another arbitrary Resume click.

## Implementation slices

1. **Typed readiness and one UI surface.** Distinguish target drift, actual
   conflicts, dirty destination, integration busy, and authority failures. Expose
   only valid actions in Changes for both modes. Preserve existing rejection rules.
2. **Durable Update & resolve.** One server-owned acknowledged operation invokes
   existing branch update/conflict assignment or Interactive reconciliation, then
   continues automatically through checks/review. Persist capture identities,
   stage and outcome; exact retries/restarts resume once. Avoid duplicate items.
3. **Useful resolution review.** Carry both sides' intended behavior and findings
   to the agents, surface resolution summaries/comparisons, and ensure real
   semantic incompatibility asks a targeted question.
4. **Authorized automatic preparation.** Add the scoped setup/approval choice,
   movement handling and destination queue behavior. Preserve exact final approval.

## Acceptance and validation

- Nonoverlapping sibling changes combine; no conflict prompt or manual chat input.
- A previously merged fix overlaps a later broader task: preserve the working
  earlier behavior, keep unique later changes, and do not reintroduce its original
  regression. Fully redundant work completes without an empty commit.
- Same-file compatible edits resolve with a scripted worker, pass checks and
  independent review, then wait for final human integration approval.
- Conflicting product intent asks a specific question; answering continues the
  same resolution without erasing task usage, findings or saved work.
- Dirty destination and external Git operations remain byte-for-byte untouched.
  Their controls do not pretend a branch update will remove those blockers.
- Restart/lost response between capture, assignment, checks and completion
  resumes the same operation. No duplicate resolution item, commit or dispatch.
- Destination advancement before apply cannot apply a stale final approval;
  movement during preparation cannot erase incoming nonconflicting changes.
- Resolution that leaves markers, deletes required incoming behavior or fails
  review never reaches integration approval as a success.
- Interactive and Unattended use the same visible preparation stages and Changes
  review while keeping their existing commit and branch history contracts.
- Unsupported binary, protected-path and evidence-size cases name the limitation
  and preserve both versions. No silent fallback to one side.

Start with `python3 -B scripts/check.py --plan`. Extend small deterministic cases
in `test_branch_conflicts.py`, `test_branch_update.py`, relevant UI/HTTP tests and
continuation tests. Reuse existing real-Git scenarios in `test_branch_merge.py`
and `test_commit_reconciliation.py`; do not add another expensive multi-item live
workflow. Measure new-test costs and obtain approval before adding heavy cases
under AGENTS.md. No live inference is needed for routine validation.

Document delivered behavior in [branch-update-recovery.md](../branch-update-recovery.md),
commit only this task's changes, and report remaining unsupported cases. The
operator handles reloads. Success is automatic arrival at a trustworthy review,
not merely another understandable stop screen.
