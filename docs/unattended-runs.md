# Interactive and Unattended work

**Work mode** beside the composer controls how you supervise a job. It is separate from model placement and the duration/budget preset.

- **Interactive** is the default. Chat, inspect changes, approve commands, and approve each proposed commit through the existing conversation.
- **Unattended** turns a prompt, a project document, or both into a finite proposal. After **Start run**, cheapoS implements, checks, independently reviews, and commits items sequentially to the inspected feature branch. You decide whether to merge the finished work.

Changing the selector alone does not request a model, create a branch, or authorize work. Drafts retain their mode and inputs; new chats default to Interactive. An authorized run keeps its mode—use Pause and Resume instead of changing its authority through the selector.

## Start with a prompt

1. Open a local Git project and choose **Work mode → Unattended**.
2. Enter: “Implement a CSV reader, Markdown output, and a CLI on a feature branch. Add deterministic tests for each part.” Send it, then choose **Start** in the form. The form closes immediately and opens the chat while cheapoS prepares the proposal. No document is required.
3. Follow progress in chat and reply to any questions or errors there. When ready, choose **Inspect proposal** to review the complete item list, criteria, checks, committed base, feature branch, target, model placement, and cumulative limits. Edit the proposal if needed; edited proposals must be prepared again before starting.
4. Click **Start run** to authorize exactly that proposal and its displayed test scope.

You can add details while planning or reply after a question, error, or pause. Replies revise the proposal in the same chat using the original captured document and remaining planning allowance. A reply received during a model request is included before a proposal can be started. Changing a ready proposal through chat invalidates its previous Start approval token.

Editing an unstarted proposal preserves its conversation and planning usage. Replacing the project, committed base, captured prompt/document, or model placement requires a fresh planning request. The selected document is not silently reread when you reply. The form’s **Start** begins planning; **Start run** still authorizes the inspected proposal.

A distinct, named reviewer is required. A second request to the same model does not count as independent review.

## Start with a document, or both

Choose Unattended and enter a readable project-relative document path such as `docs/utility-plan.md`. Submit with an empty prompt to plan directly from that document; pasted text and Markdown checkboxes are unnecessary. The document must be nonempty UTF-8 text, at most 64 KB, and accessible through the project's file restrictions.

For combined input, select the document and add a prompt such as “Complete this plan, preserving the existing CLI interface.” The prompt and the document's captured path, contents, and hash stay separate. Conflicting scope needs clarification before authorization. An unreadable document is an error, not permission to omit it. Later file edits do not silently change the captured proposal.

## Triggers

| Your action | Result |
| --- | --- |
| Choose Unattended, submit a prompt/document, then **Start** | Open the chat immediately and prepare a bounded plan in the background; no implementation or feature branch yet. |
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

Keep task storage outside the project being edited. In particular, when using cheapoS to work on its own repository, launch it with `python3 run.py --data-dir ../cheapos-task-storage`; the default `.cheapos` directory is inside this repository. Overlapping source and task directories are rejected.

The private task copy starts at the inspected committed base. Existing source edits remain untouched and are excluded from the run. Local commits advance a newly owned feature branch while preserving excluded source paths; they do not update your target checkout or count as your final acceptance.

Supported unittest profile grants can cover multiple selectors. Other authorized checks retain their exact command scope. These permissions expire when the server restarts; changed executables, configuration, or workspace identity require revalidation. Tests execute local project code: the task copy is not an operating-system sandbox. Initial run approval does not grant arbitrary commands, installation, paid escalation, push, or merge.

Items, retries, model requests, tool actions, working time, tokens, and cost share cumulative limits. Pausing or restarting does not refill them. Restart preserves progress but never automatically resumes execution. Resume may ask you to inspect a renewed command grant; a retained merge operation has a separate explicit recovery action.

Final check failures and reviewer corrections can produce at most three bounded repair items, preserving original commits and using the original criteria, checks, and remaining limits. Operator corrections also use this allowance and require confirmation of their proposal. Repairs spanning more than twelve distinct original criteria need a smaller explicit amendment. New requirements, broader commands, different models/destinations, or increased limits require a new authorization rather than an implicit expansion.

## Finish the branch

Final review covers the cumulative diff, every requirement, all item receipts, and final integration checks. Large reviews use explicit chunk coverage; oversized or incomplete evidence cannot become a passing review.

The final view offers **Request changes**, **Leave on feature branch**, and **Approve & merge locally**. A stale preview, dirty target, or diverged target keeps the saved diff readable while disabling merge. Resolve the stated blocker and refresh or explicitly recheck as needed.

Integration supports local fast-forward only. A checked-out target must be clean and in the selected source checkout. External branch movement, another worktree holding the target, or divergence prevents integration; cheapoS does not force-update, rebase, resolve conflicts, push, or open a pull request. After success, it reports the target and SHA and asks what to work on next.

Unattended does not schedule wakeups or keep executing after the server stops. Deterministic fixtures test controller behavior and interruption recovery; they do not establish real-model quality, reliability, or savings. A subsequent live trial is a separate operator action with selected models and a known budget.

## Measurement runs for live trials

When gathering baseline evidence, select **Measurement run · track usage without
work limits** in the planning dialog. This applies during planning and execution
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
