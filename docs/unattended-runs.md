# Interactive and Unattended work

**Work mode** beside the composer controls how you supervise a job. It is separate from model placement and the duration/budget preset.

[See where to change Work mode, with a screenshot and examples →](USER_GUIDE.md#work-modes)

- **Interactive** is the default. Chat, ask questions, explore ideas, and steer changes as you go. Code changes get checks and model review; you approve each commit to your project.
- **Unattended** turns a prompt, a project document, or both into a finite proposal. After **Start run**, cheapoS implements, checks, independently reviews, and commits items sequentially to the inspected feature branch. You decide whether to merge the finished work.

Changing the selector alone does not request a model, create a branch, or authorize work. Drafts retain their mode and inputs; new chats default to Interactive. An authorized run keeps its mode—use Pause and Resume instead of changing its authority through the selector.

## Start with a prompt

1. Open a local Git project and choose **Work mode → Unattended**.
2. Enter: “Implement a CSV reader, Markdown output, and a CLI on a feature branch. Add deterministic tests for each part.” Send it to prepare the proposal directly in Chat. No setup popup or document is required. Optional **Planning settings** beside the composer expose committed-base, target, feature-branch, and measurement overrides before Send.
3. Follow progress in chat and reply to any questions or errors there. When ready, choose **Review & start** to review the complete item list, criteria, checks, committed base, feature branch, target, model placement, and cumulative limits. Edit the plan, checks, branches, or execution allowances in that screen. **Validate changes** checks the edited contract and keeps Start disabled until it is current.
4. Click **Start run** to authorize exactly that proposal and its displayed test scope.

You can add details while planning or reply after a question, error, or pause. Replies revise the proposal in the same chat using the original captured document and remaining planning allowance. A reply received during a model request is included before a proposal can be started. Changing a ready proposal through chat invalidates its previous Start approval token.

Editing an unstarted proposal preserves its conversation and planning usage. Replacing the project, committed base, captured prompt/document, or model placement requires a fresh planning request. The selected document is not silently reread when you reply. **Send** begins planning with the configured planner and existing allowance; **Start run** authorizes the inspected execution proposal. Later execution-budget or measurement edits cannot enlarge the original planning allowance.

A distinct, named reviewer is required. A second request to the same model does not count as independent review.

## Start with a document, or both

Choose Unattended and enter a readable project-relative document path such as `docs/utility-plan.md`. Submit with an empty prompt to plan directly from that document; pasted text and Markdown checkboxes are unnecessary. The document must be nonempty UTF-8 text, at most 64 KB, and accessible through the project's file restrictions.

For combined input, select the document and add a prompt such as “Complete this plan, preserving the existing CLI interface.” The prompt and the document's captured path, contents, and hash stay separate. Conflicting scope needs clarification before authorization. An unreadable document is an error, not permission to omit it. Later file edits do not silently change the captured proposal.

## Triggers

| Your action | Result |
| --- | --- |
| Choose Unattended and **Send** a prompt/document | Open the chat immediately and prepare a plan in the background; no implementation or feature branch yet. |
| In Interactive, explicitly request “Start a branch run” or “Implement this job on a feature branch” | Offer a work-mode choice. Choosing the unattended proposal opens planning. |
| Mention a branch, select a document without submitting, quote a trigger, or ask for an explanation/summary | Keep ordinary chat behavior; no automatic run authorization. |
| **Start run** | Authorize the inspected revision, branch, models, limits, and shown checks. |
| **Pause** / **Resume** | Stop continuation / revalidate the saved run and remaining allowance. |
| **Request changes** | Show a bounded correction proposal; confirming it authorizes that correction. |
| **Refresh preview** or load another diff page | Read saved work and check its validity without requesting models or rerunning tests. |
| **Recheck changes** | Explicitly resume final verification and review within the remaining allowance. |
| **Approve & merge locally** | Authorize the inspected local integration only. |

A document or prompt saying “merge when done,” model output, or a quoted instruction cannot replace the merge button. If an Interactive request does not offer planning, select Unattended explicitly.

## While the run works

Chat keeps live thinking and command output inside the active cheapoS work step,
which opens automatically. Collapse it to keep a short updating preview. Details
group routine exploration while keeping edits, failures, and review feedback
easy to inspect. **Routing & request details in Technical logs** opens the
retained candidate and request diagnostics separately from the work stream.

Keep task storage outside the project being edited. In particular, when using cheapoS to work on its own repository, launch it with `python3 run.py --data-dir ../cheapos-task-storage`; the default `.cheapos` directory is inside this repository. Overlapping source and task directories are rejected.

The private task copy starts at the inspected committed base. Existing source edits remain untouched and are excluded from the run. Local commits advance a newly owned feature branch while preserving excluded source paths; they do not update your target checkout or count as your final acceptance.

Supported unittest profile grants can cover multiple selectors. Other authorized checks retain their exact command scope. These permissions expire when the server restarts; changed executables, configuration, or workspace identity require revalidation. Tests execute local project code: the task copy is not an operating-system sandbox. Initial run approval does not grant arbitrary commands, installation, paid escalation, push, or merge.

Items, retries, model requests, tool actions, working time, tokens, and cost share cumulative limits. Pausing or restarting does not refill them. Restart preserves progress but never automatically resumes execution. Resume may ask you to inspect a renewed command grant; a retained merge operation has a separate explicit recovery action.

If an item reviewer keeps returning invalid decisions, repeating unchanged reads,
or failing to reach a decision after reassessment, automatic remote runs select
another eligible independent reviewer before pausing. Chat shows the handoff. The
replacement receives the current patch, criteria, check evidence, unresolved
findings and operator guidance; the worker does not start over. Valid requests
for changes return to the worker rather than searching for an easier approval.

Failed review exchanges remain saved. Resume on an older stalled item uses this
same recovery path and excludes reviewers that already failed that candidate.
Runs continue through unused eligible reviewers within the remaining authorized
work and spending limits. There is no additional handoff-count cutoff. No run
repeatedly cycles through failed reviewers or resets cumulative usage. Manual placement and explicitly chosen reviewers stay
pinned: **Choose reviewer** authorizes a replacement for this task. Missing
identity evidence, exhausted allowances, or unavailable authorized routes still
need the specific action shown in the pause.

Final check failures and reviewer corrections can produce at most three bounded repair items, preserving original commits and using the original criteria, checks, and remaining limits. Operator corrections also use this allowance and require confirmation of their proposal. Repairs spanning more than twelve distinct original criteria need a smaller explicit amendment. New requirements, broader commands, different models/destinations, or increased limits require a new authorization rather than an implicit expansion.

## Finish the branch

Final review covers the cumulative diff, every requirement, all item receipts, and final integration checks. Large reviews use explicit chunk coverage; oversized or incomplete evidence cannot become a passing review.

Open **Changes** to inspect the cumulative diff, saved verification evidence, and merge controls. **Review changes** in Chat opens this same workspace, with immediate loading feedback while the saved preview is prepared. Opening it does not rerun tests. **Plan** contains only the approved scope, acceptance criteria, and item progress; **View plan** lets you consult it and return to Changes without losing your place. Interactive patch reviews also live in Changes, with their own approval to commit.

Choose a file from the searchable list to read its colored diff with old/new line numbers. **Wrap lines** avoids horizontal scrolling; **Raw patch** shows the original Git patch. Optional **Mark reviewed** controls track your place in the current preview. File selection, scroll position, and marks survive switching tabs; refreshing the preview or opening another task starts a fresh checklist. The check/review summary opens saved commands, results, reviewer feedback, and exact revisions.

The review offers **Request changes**, **Leave on branch**, and **Approve & merge locally**. Request changes returns you to Chat to describe a correction. A stale preview, dirty target, or diverged target keeps the saved diff readable while disabling merge. All diff pages must finish loading before merge is available; review marks are optional and do not authorize integration. Resolve the stated blocker and refresh or explicitly recheck as needed.

Integration supports local fast-forward only. A checked-out target must be clean and in the selected source checkout. External branch movement, another worktree holding the target, or divergence prevents integration; cheapoS does not force-update, rebase, resolve conflicts, push, or open a pull request. After success, it reports the target and SHA and asks what to work on next.

Unattended does not schedule wakeups or keep executing after the server stops. Deterministic fixtures test controller behavior and interruption recovery; they do not establish real-model quality, reliability, or savings. A subsequent live trial is a separate operator action with selected models and a known budget.

## Measurement runs for live trials

When gathering baseline evidence, select **Measurement run · track usage without
work limits** under the composer’s optional **Planning settings**, before Send. This applies during planning and execution
and is displayed again before Start. The run summary identifies measurement runs.
For operator-driven trials through the API, pass `measurement: true` to
`POST /api/branch-runs/plan-start` (returns `task_id` before inference completes),
or the synchronous `POST /api/branch-runs/plan`; a directly prepared plan uses
`plan.measurement: true`. Both prompts and selected documents are supported.
Models cannot select this option themselves. Start binds the choice into the
proposal's authorization; it cannot silently change on Resume or final review.

Measurement mode disables cumulative worker-turn, request, tool-action,
reviewer-token and working-time caps, and check execution deadlines. Checkpoint
intervals do not interrupt implementation. Accounting continues: worker and
reviewer tokens (including pending reservations), estimated/reported costs,
requests, tool actions, working time, check durations, per-request model IDs,
provider time and outcomes remain recorded across pauses and restarts. Completed
checks record `allowed_seconds: null` when there was no deadline. These are
actual uncapped work counters, not arbitrarily large numeric budgets.

The spending cap and model-placement policy remain active: use the existing
$0/free-remote policy for these trials. Measurement is not permission for a paid
fallback. Per-response token/context capacities, provider connection timeouts,
output-size protections and finite malformed-response/non-progress/review repair
attempts remain technical boundaries. A genuine error or missing user input may
still pause a run. Pause continues to cancel a running check without a deadline.
Normal bounded runs retain their existing limits.

Record successful and failed attempts separately, including interventions,
completion status, model IDs, request counts, tokens, elapsed working time and
check durations. Use distributions across comparable completed tasks to choose
later limits; do not infer a cap from one small success or hide retries by
resetting counters. No default limits have been inferred from the first trial.


## Context and readiness before unattended execution

New proposals inspect a bounded repository inventory, manifests and project guidance before planning. The planner can request additional scoped, read-only files. Repository content is evidence, not permission. Existing app type, stack, structure and UI conventions should be discovered from the project; reversible implementation choices follow those conventions. Planning assumptions appear in the proposal and are included in the accepted item instructions.

The proposal shows working-directory readiness and observable prerequisites for every planned check. Start rechecks these prerequisites before granting authority. This is not a test run or a live model probe: undeclared dependencies, later environment changes and provider quota remain unverified. Starting authorizes reads/edits in the private working copy and the displayed commands (including a displayed test profile where applicable). A remembered additional command is granted exactly, rather than silently broadening its scope.

During new unattended runs, the first clarification attempt for each item returns project context and directs the worker to inspect before interrupting. An essential unanswered decision can still pause the run on the next attempt. This check is durable and happens at most once per item. It does not grant new commands, installations, external effects or destructive actions.

New proposals include `continue_independent: true` in their signed plan. A question-blocked item can be deferred when its workspace is clean, no operation is pending, and another item has completed dependencies. Work with unfinished edits remains paused. When no runnable items remain, the questions are surfaced for operator guidance. Final verification checks receipts in actual execution order and enforces dependencies. Setting the plan field to `false` retains sequential execution; previously accepted plans are unchanged.

Validation for this change used focused scripted/pure checks without live inference. The 24-test setup, scheduling, start, reprepare, execution and state selection passed in 43.257 seconds; the new pure setup and scheduling cases took milliseconds. Existing planner, command-permission and UI markup checks also passed. Browser rendering and the next live easy-task trial remain to be verified.

Planner discovery exhaustion is handled as a proposal correction, not a model-routing failure. The final permitted read explicitly directs the planner to propose from collected evidence. A stale extra read is rejected locally without executing it or consuming a model handoff. Already-exhausted planning attempts remain saved; Activity offers New planning chat rather than a Resume action that cannot renew recovery.

## Using another chat while work runs

One Interactive conversation can run alongside one Unattended run or planning
conversation. Each has its own task copy, model binding, usage, command approvals
and Pause state. Items within an Unattended plan still run in order. This does not
raise either task's authorized spending limit or enable a paid fallback.

The server admits at most one live task of each mode. A further task stays a
draft, or **Saved, not started** if creation already succeeded. Send, Enter and
the saved-task retry use the same capacity decision. Follow the displayed link to
the occupying task, or wait for its slot to become available and retry explicitly.
There is no automatic queue. A lost start response is checked against that same
saved task, rather than creating another one.

Local inference and verification commands each have one shared execution slot.
A waiting task shows its resource wait and can be paused independently; waiting
does not refill its budget. Remote requests retain shared provider cooldowns and
probe coalescing. Integration into the same Git repository is serialized and
still requires fresh expected-tip, cleanliness and approval checks. No task can
merge another task's patch under its own approval. Restart pauses saved tasks;
it does not automatically resume them.

Installation-wide accounting is available from **Usage & savings** in the sidebar;
see [coverage and export details](development/lifetime-usage.md).

## Optional coordinator recovery

In **Execution settings**, choose **Coordinator assistance — recommended → On**
and an installed local model. Off remains fully supported. The choice applies to
new tasks and proposals; it does not change the worker/reviewer placement or opt
an existing run into local inference. Saving makes no inference request.

The composer displays the current chat's captured On/Off choice. Eligible paused
Interactive chats offer a separate **Enable coordinator & reassess** action for
one unused consultation with their saved local model. This explicit action does
not apply to Unattended runs or change their approved plan authority. Restarting
alone enables nothing, and changing new-chat defaults leaves existing runs intact.

After repeated worker inspection has resisted a focused recovery step, the
coordinator may inspect a bounded packet of saved evidence and suggest one useful
next action. It can request a genuinely new file excerpt through the worker;
you should not have to paste repository code merely because the worker repeated
another read. Advice does not authorize commands or replace independent review.

There is at most one consultation per Interactive request or Unattended item,
with one announced format correction if the local reply is not valid JSON.
Both calls use existing limits; failed format correction does not repeat. Older
eligible paused Interactive chats offer **Retry coordinator format** for an unused
correction against the same saved work, without another chat prompt.
**Coordinator helping** appears in the same reply with actual output and Details.
The coordinator returns to idle afterward. Unavailable or ignored assistance
falls back to existing recovery. A real unanswered question still needs your reply;
a worker stall is labeled separately. Resume does not renew consumed attempts.
See the [recovery contract and validation](development/coordinator-assisted-recovery.md).
