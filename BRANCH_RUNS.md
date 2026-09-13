# cheapoS next milestone: complete a job on a feature branch

**North star:** give cheapoS a bounded job, see it implement, test, review, and commit each part, then make one final decision about the finished branch.

This is the implementation companion to [TASKS.md](TASKS.md), continuing after completed cards T01–T27. Start with **T28**, then follow the dependency order below. These are implementation instructions for future work, not a statement that branch runs already exist.

## Why this milestone

The project started with [Irushi's post about a slower Codex mode](https://x.com/Im_IrushiK/status/2098809262302720347). The operator supplied its text: the motivating idea was to trade immediate speed for more available usage, hand off a goal before sleep, and inspect the result in the morning. The post itself was not retrievable during this check-in; this description uses the supplied text.

cheapoS's version of that ambition is **more completed, useful work for less money and less operator attention**. Slower inference alone does not reduce tokens or prove lower bills. Free availability, appropriate model selection, bounded recovery, and avoiding repeated work must produce measurable results. Do not introduce artificial delays or claim a fixed savings percentage.

The ownership split stays simple: cheapoS decides what work to do and when another opinion is needed; OmniRoute supplies eligible model routes. Local-only/manual operation remains supported. Branch autonomy requires the independent reviewer contract below; a single local model is not silently represented as two independent models.

## The operator experience

1. Open a project and say, for example, “Implement the three utilities in docs/utility-plan.md on feature/utilities.” Natural language and ordinary documents work; Markdown checkboxes are optional.
2. cheapoS shows a compact run proposal: ordered tasks, completion criteria, base branch/commit, new feature branch, model placement, total limits, test permission scope, and the final check command. One **Start branch run** action authorizes that proposal. Existing adequate session grants need no second click.
3. cheapoS creates the branch and an isolated task copy. It completes one planned item at a time: implement → required checks → independent review → automatic local feature-branch commit → next item.
4. Routine test failures and reviewer requests return to the worker. Real missing information, exhausted recovery, changed authority, or hard limits produce a specific pause. Pause stays beside the chat composer throughout.
5. After all items, cheapoS runs the agreed final integration checks and performs a final review of the combined work. The operator sees the cumulative diff, task outcomes, and commit history in Chat.
6. The operator may request changes, leave the branch as it is, or **Approve & merge locally**. The first version supports a checked, fast-forward integration. Publishing, PR creation, squash/rebase, and conflict resolution at integration are separate future features.
7. After integration, cheapoS reports the target branch and resulting SHA, then asks what to work on next. A branch commit is never presented as a merge or as human acceptance.

Example progress, generated from actual controller events:

> cheapoS: CSV parser completed. Checks passed and the reviewer approved it. Committed `abc1234` to `feature/utilities`. Starting Markdown output, task 2 of 3.
>
> Working on Markdown output · Details
>
> All three tasks are complete. Final checks and review passed. Your branch is ready for review.

## Read this before implementing

Inspected baseline: `1178dd7` on `work/resizable-panels`, with T01–T27 available at `39903c9` and included in local `main`. The first milestone recorded 387 passing Python tests and 70 passing JavaScript tests; the subsequent panel commit adds its own coverage. These are historical results, not validation of the new cards. Re-read current code and `git status` before editing.

Important existing behavior:

- Backend: Python 3.9+ standard library. Frontend: vanilla JavaScript in `dist/`, without a build step. Keep this stack.
- `Engine` owns a live mutable task; `Store.get()` returns copies. Metadata is separate. Use one owner for run execution state so polling, approvals, and worker saves cannot overwrite each other.
- `Workspace.snapshot()` copies eligible **working-directory** files into a separate Git repository, including eligible untracked files. It does not preserve source ancestry. Branch runs need a new snapshot-from-commit path; do not silently change existing chat snapshots.
- `commits.prepare()` requires a clean source checkout; `apply_and_commit()` changes its index/files and advances its checked-out branch. **Do not call that operation after each branch-run item.**
- `Engine.commit_task()` refuses commits while any runtime is alive. Branch commits need a controller-owned internal transition, not a bypass of the manual HTTP endpoint or its safeguards.
- `Engine.reviewed_patch()` allows a manual takeover-completed path. Automatic commits must explicitly require a distinct reviewer APPROVE; status `completed` is insufficient.
- T13 verification identity includes workspace, baseline, patch, command, executable/dependencies, configuration, and generation. Advancing a baseline changes this identity even if content stays identical. Keep immutable commit evidence receipts; do not manufacture a passing record for the next patch.
- `ProjectTestGrants.register()` currently accepts specific saved workspace paths. New destinations must be explicitly registered by the controller. Grants expire on server restart and remain subject to runner/configuration changes.
- `Engine.start()` and `Runtime` have per-start/per-request counters; starting the next item must not renew the overall branch-run budget. Usage reservations and uncertain requests stay accounted.
- Existing conversation helpers ask “what next?” after a commit; branch item commits instead announce the next item. Only the final completed integration closes the whole job.
- Existing commit acceptance feeds model ranking. Automatic commits must not count as operator acceptance; record that separately at the final human action.
- Patch size limits currently include 30,000 characters for a checkpoint and 100,000 for refreshed changes. A cumulative diff cannot simply be stuffed into one old checkpoint or silently truncated.

## Fixed design decisions for the first version

### Workspace and branch ownership

Prefer the existing **private, filtered task repository** as the execution workspace, populated from a pinned source commit. Advance a newly owned feature ref in the source repository using a temporary index and conditional ref updates. This avoids exposing the source repository's Git metadata to the workspace and fits current tools. Do not add a linked worktree merely to replace a working snapshot mechanism.

The private snapshot and the feature branch have different Git ancestry. Record their mapping explicitly. Build each source commit by applying the item's exact patch over the previous full source tree; preserve all excluded source paths unchanged. Never replace the source tree with the filtered snapshot tree. Retain symlink, secret-path, size, and file-tool exclusions.

Initial runs start from a committed base; dirty source edits remain untouched and are not included. Show that fact in the start proposal. Capturing uncommitted source changes is a later feature. Use a new, explicitly authorized `refs/heads/...` destination. Never adopt an unrelated existing branch, overwrite a ref, or advance a branch checked out in any operator worktree. A branch registered to this run may be resumed after ownership and tip checks.

Identify the intended integration target from local repository configuration and the operator's selection. Refuse automatic feature commits to that target, detected default refs, and configured protected refs. A name prefix is only a suggestion, not permission. Do not claim to know remote hosting branch-protection rules without reading them; this milestone makes no network call to discover them.

Conditional ref updates and a durable operation journal are required. Git's expected-old-value update protects against advancing an unexpectedly moved ref; it does not make a Git operation and a JSON save one atomic transaction. See [git-update-ref](https://git-scm.com/docs/git-update-ref). Inspect checked-out branches through Git's worktree inventory rather than only the source `HEAD`; see [git-worktree](https://git-scm.com/docs/git-worktree).

### Authority, failure recovery, and budgets

Run authorization is an operator action bound to the validated plan revision, project identity, exact feature ref/base, model-placement policy, and limits. A document, model tool call, reviewer statement, or stored event cannot grant it. Keep the normal per-patch manual workflow unchanged for other tasks.

Authorization permits automatic local commits only after the item's required current checks and independent reviewer approval. It does not grant arbitrary shell execution, network access beyond existing settings, paid escalation, installation, push, or merge. Tests execute locally; a feature branch is not an OS sandbox.

The plan has finite items and acceptance criteria. Use one cumulative cost/usage ledger, working-time allowance, and bounded recovery policy across all items, retries, and resumes. A task-count ceiling bounds the accepted plan, not an arbitrary five-commit interruption halfway through authorized work. Pause and normal server restarts never silently renew allowances. Paused/offline time is distinct from working time; persist elapsed active time conservatively, and charge authorized route waiting as working time. No scheduled wakeups or automatic execution on server launch in this milestone.

Supported session test grants may cover every item in the registered run workspace. They expire on restart. A restart preserves progress and the run contract; explicit Resume and any expired command grant must be revalidated before execution. Normal uninterrupted operation should need no per-item prompts.

### What counts as complete

An item needs acceptance evidence and, for changed code, the planned checks plus a reviewer approval tied to that exact candidate. A spoken “done” or an empty patch is not enough. Already-satisfied items require an explicit, reviewed no-change outcome and create no empty commit. Unsupported/missing verification is a setup pause, not a green check.

After all items, final integration checks apply to the final contents. A final reviewer checks the complete accepted plan against an exhaustive, bounded manifest of the combined changes and evidence; large diffs require explicit chunk coverage, not silent omission. Review revisions append ordinary new work/commits and invalidate final readiness. Keep original item history.

The final approval binds the inspected feature tip, target ref/tip, cumulative diff, and readiness evidence. Recheck all of them at integration. The first merge action supports only fast-forward cases; target divergence must produce a clear saved-branch outcome, never a force update or unreviewed merge. The checked-out-target path must update files/index consistently through Git, not only move its ref. See [git-merge](https://git-scm.com/docs/git-merge).

## Ordered implementation cards

All cards below start **Todo**. Sizes describe scope, not time. Dependencies mean implemented, validated, and available commits. T01–T27 are baseline prerequisites; do not redo them.

| ID | Task | Depends on | Size | Status |
| --- | --- | --- | --- | --- |
| [T28](docs/tasks/T28-branch-run-state.md) | Durable run plan, item states, and compatibility | T01–T27 | M | Todo |
| [T29](docs/tasks/T29-branch-workspace.md) | Snapshot from a committed base and owned feature ref | T28 | L | Todo |
| [T30](docs/tasks/T30-branch-authorization.md) | One run authorization and scoped test permissions | T28, T29 | M | Todo |
| [T31](docs/tasks/T31-branch-evidence.md) | Exact candidate evidence and independent review gate | T28, T29 | M | Todo |
| [T32](docs/tasks/T32-branch-autocommit.md) | Journaled automatic commits to the owned ref | T30, T31 | L | Todo |
| [T33](docs/tasks/T33-branch-execution.md) | Sequential execution, recovery, and shared limits | T32 | L | Todo |
| [T34](docs/tasks/T34-branch-resume.md) | Pause/restart recovery and branch drift handling | T33 | M | Todo |
| [T35](docs/tasks/T35-branch-start-ui.md) | Document-to-plan proposal and simple start flow | T30, T33, T34 | M | Todo |
| [T36](docs/tasks/T36-branch-progress-ui.md) | One cheapoS conversation with visible milestones | T33, T35 | M | Todo |
| [T37](docs/tasks/T37-branch-final-readiness.md) | Combined verification, review, and revision loop | T31, T33, T34 | L | Todo |
| [T38](docs/tasks/T38-branch-final-review-ui.md) | Cumulative diff and one final decision | T36, T37 | M | Todo |
| [T39](docs/tasks/T39-branch-local-merge.md) | Explicit local integration and conversation close | T32, T37, T38 | L | Todo |
| [T40](docs/tasks/T40-branch-end-to-end.md) | Three-task end-to-end proof and user documentation | T28–T39 | M | Todo |

Do these sequentially in this shared checkout. Do not dispatch multiple models to edit the same engine/UI files. Lower-level helpers may be callable by deterministic tests before UI exists, but no incomplete automatic-run action should appear usable to the operator.

## Copy this handoff prompt

```text
Implement only docs/tasks/T28-branch-run-state.md.
Read AGENTS.md, BRANCH_RUNS.md, the task card, and CONTRIBUTING.md first.
Inspect git status and current code. Verify completed dependencies; do not
implement missing adjacent cards or invent their APIs as if they already exist.
TASKS.md is the completed first milestone; BRANCH_RUNS.md is the active board.

Follow this card's behavior, edge cases, non-goals, and acceptance criteria.
Make small complete edits and preserve existing manual chat/commit behavior.
Treat proposed names as new contracts, not pre-existing functions. Document any
equivalent design change and update dependent cards if it affects their contract.
Use deterministic providers and temporary Git repositories for verification.
Do not use personal API keys, a live user task, or the source checkout as a fixture.
Do not implement automatic merge/push, unrestricted commands, or extra features.

Run the focused checks, required browser scenario, and CONTRIBUTING gate as
applicable. Record actual results; do not claim a browser/live-model check passed
if it did not run. Update the card's completion record and its BRANCH_RUNS.md row.
Commit only your work per AGENTS.md and report the commit, tests, and limitations.
Do not start the next card automatically unless separately instructed.
```

Change only the card path as work progresses. If implementing inside cheapoS before this feature is complete, use its existing reviewer/human commit flow. These planning documents do not authorize a model to bypass that flow through a test command. Direct coding agents follow the repository's existing commit instructions.

If a card cannot fit one attempt, finish a coherent boundary, mark **In progress**, and list the exact remaining acceptance items. Do not mark Done, remove requirements, or run an endless repair loop. Split a remaining bounded follow-up explicitly if needed.

## Validation and definition of done

Follow [CONTRIBUTING.md](CONTRIBUTING.md). During iteration, use focused selections such as `python3 -B scripts/dev_tests.py --pattern test_branch_runs.py`; filenames in new cards are proposals until created. For frontend work, run `node --check dist/app.js`, the relevant Node tests, and an isolated browser scenario. New static modules need the HTML reference and server allowlist entry.

Use real temporary Git repositories for branch, index, ref, conflict, and crash tests; scripted providers for inference; actual subprocesses for cancellation/check evidence. Test the feature's transaction, not a mocked success string. Full-suite gates belong at required integration/release boundaries, not at every unchanged UI or approval stage. The previous full Python gate took about seven minutes; allow at least 600 seconds and record the actual new duration.

Every card has a completion record. Fill it and update this board in the implementation commit. Report its SHA in the handoff rather than creating another commit to insert its own SHA. Browser checks are required for UI cards and the final milestone; unavailable checks remain explicit limitations.

The final proof is a three-item run with a failing test repaired and a reviewer revision resolved, three meaningful feature commits, zero intermediate operator clicks after initial authorization, an exhaustive final diff, a requested follow-up revision, and one approved local merge. Repeat recovery scenarios with interruption, exhausted limits, and external branch changes. Ordinary manual chat/approval must still work.

Report completed outcomes, intervention counts/reasons, elapsed and active time, retries, tokens with provenance, and accounted cost. Scripted providers prove controller behavior, not real model quality or savings. A subsequent real-model trial is an explicit operator action with selected routes and a known budget; it is not required to mark deterministic implementation complete.

## Next check-in: cheapoS builds its next feature

The agreed sequence is **implement this workflow first, then choose the next product feature for cheapoS to implement through it**. Do not bundle that feature into these cards or select it before seeing the completed workflow's limitations.

After T40, review the results with the operator and choose one useful, bounded cheapoS improvement with two or three dependent parts, clear acceptance criteria, and deterministic tests. Prefer ordinary app functionality with an observable end result. Avoid making the first unattended trial rewrite this run controller, its permissions, or its own approval/commit rules.

Write the selected feature as a small spec that the running cheapoS app can consume. Submit it through the actual branch-run UI on a fresh feature branch using explicitly selected models and a known budget. Let cheapoS's workers/reviewer perform the implementation, checks, commits, and final handoff; the external implementing model should observe and diagnose rather than secretly finish the feature for it. A necessary intervention is recorded as an intervention, not hidden to make the experiment appear successful.

Keep the currently running app on its stable committed version while cheapoS builds the trial in its private copy. Exercise the candidate UI in an isolated preview if needed. The operator inspects the final cumulative diff and chooses whether to integrate it; update/restart the running app only at an appropriate boundary afterward.

Success means the real feature works, its tests/review support the result, the source checkout stayed undisturbed during execution, and the operator did not have to repeatedly rescue routine steps. Report actual time, route changes, usage/cost provenance, and interruption reasons, including a failed or partial outcome. This real-model trial tests the product promise; it is separate from the scripted T40 controller proof.

## Deliberately later

Automatic publishing/PRs; squash/rebase and automatic target-conflict resolution; parallel task execution; automatic scheduling/overnight wakeups; inherited uncommitted edits; unrelated existing-branch adoption; persistent command trust; more test-runner profiles; automatic dependency installation; runtime compression tools. Each needs its own bounded task after this loop works.
