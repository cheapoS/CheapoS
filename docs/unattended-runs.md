# Interactive and Unattended work

**Work mode** beside the composer controls how you supervise a job. It is separate from model placement and the duration/budget preset.

- **Interactive** is the default. Chat, inspect changes, approve commands, and approve each proposed commit through the existing conversation.
- **Unattended** turns a prompt, a project document, or both into a finite proposal. After **Start run**, cheapoS implements, checks, independently reviews, and commits items sequentially to the inspected feature branch. You decide whether to merge the finished work.

Changing the selector alone does not request a model, create a branch, or authorize work. Drafts retain their mode and inputs; new chats default to Interactive. An authorized run keeps its mode—use Pause and Resume instead of changing its authority through the selector.

## Start with a prompt

1. Open a local Git project and choose **Work mode → Unattended**.
2. Enter: “Implement a CSV reader, Markdown output, and a CLI on a feature branch. Add deterministic tests for each part.” Send it, then choose **Prepare proposal** in the planning form. No document is required.
3. Inspect the complete item list, criteria, checks, committed base, feature branch, target, model placement, and cumulative limits. Edit the proposal if needed; edited proposals must be prepared again before starting.
4. Click **Start run** to authorize exactly that proposal and its displayed test scope.

Editing an unstarted proposal preserves its conversation and planning usage. A different project, committed base, captured prompt/document, or model placement requires a fresh planning request.

A distinct, named reviewer is required. A second request to the same model does not count as independent review.

## Start with a document, or both

Choose Unattended and enter a readable project-relative document path such as `docs/utility-plan.md`. Submit with an empty prompt to plan directly from that document; pasted text and Markdown checkboxes are unnecessary. The document must be nonempty UTF-8 text, at most 64 KB, and accessible through the project's file restrictions.

For combined input, select the document and add a prompt such as “Complete this plan, preserving the existing CLI interface.” The prompt and the document's captured path, contents, and hash stay separate. Conflicting scope needs clarification before authorization. An unreadable document is an error, not permission to omit it. Later file edits do not silently change the captured proposal.

## Triggers

| Your action | Result |
| --- | --- |
| Choose Unattended, submit a prompt/document, then **Prepare proposal** | Request a bounded plan; no implementation or feature branch yet. |
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
