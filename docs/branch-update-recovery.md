# Update & resolve

When the target branch advances during a task, open **Changes** and choose **Update & resolve**. This explicitly approves combining the inspected target into the saved task branch. It does not merge into the target or push anything.

The controller requires completed items, an idle task, a clean private copy, unchanged branch ownership and a current preview. It creates a merge commit that preserves both histories and journals the update before changing the private copy or feature ref. An interrupted update resumes through the saved preparation operation. Existing item receipts and usage remain saved; previous final approval is archived. The combined candidate must pass the authorized final checks and independent review before **Approve & merge locally** becomes available.

Conflicts stop preparation without modifying either checkout or branch. Uncommitted edits and unrelated branch movement are retained and reported, never automatically reset or stashed. The same preparation operation assigns those conflicts to the agents with captured evidence.

Regression coverage uses small controller/receipt and UI tests. Real divergent-branch, interrupted-update, and final-review smoke checks reuse existing disposable Git fixtures during development rather than adding a slow recurring agent workflow.

## Agent-assisted conflicts

If the update detects conflicts, the saved operation assigns an explicit new item to the existing worker and reviewer. The item retains the original task, usage, model policy, spending allowance and verification commands. Agents can read frozen base/task/target/suggested versions with `read_merge_context`; this does not grant arbitrary access to the source checkout. The suggested versions contain Git’s automatic combination and any unresolved markers. Agents must incorporate incoming nonconflicting changes as well as resolve conflicts.

After the resolution passes item checks and independent review, the controller records the merge ancestry without changing the reviewed tree. Final checks and review run before human merge approval. The controller journals this operation for recovery after interruption. An incompatible product choice uses the existing evidence-backed clarification flow; routine code conflicts remain agent work. Binary or oversized conflict evidence is reported explicitly instead of silently omitted.

## Unified preparation (T92)

**Update & resolve** now saves an acknowledged preparation operation before Git
inspection, and the server continues through branch update or Interactive
reconciliation into existing checks and independent review. A text conflict
assigns the existing evidence-bound resolution item automatically; it no longer
requires a second operator action. The destination remains untouched until the
normal exact-result human integration approval.

The operation is stored on the original task as `integration_preparation`.
Duplicate requests return its receipt; restarting resumes the saved update
journal, conflict item or reconciled workspace rather than creating another.
Destination edits and existing Git operations remain untouched and are checked
again at paced intervals. Repository admission continues to serialize destination
writes. The operator can still pause model work and decide genuinely incompatible
behavior through the existing conversation.

Readiness distinguishes target movement, uncommitted files, repository admission,
external Git operations, ownership, authority and current review. Only relevant
actions appear. Unsupported text decoding, file modes, protected paths and context
size retain the versions and report the exact limitation and affected paths.
The conflict comparison identifies the task revision before preparation and its
current combined candidate; it supplements the final integration diff.

New proposals may explicitly capture **Keep this task up to date before final
review**. Its saved authority binds the target branch and captured commit and
permits only descendant updates within the existing task policy. Older tasks gain
no automatic permission. A moved destination invalidates final consent: fresh
preparation and fresh final human approval are required.

An empty patch after reconciliation is marked already included only after current
checks and independent review; it never manufactures a commit or merge. Resolution
workers are instructed to preserve both incoming behavior and unique task work,
including nonconflicting incoming files, and final review still covers the original
criteria. No update broadens test commands, spending or model authority.

The new continuation tests use in-memory executors and fake timers (15 tests,
about 0.09 seconds in isolation). Existing real-Git completion and authorization fixtures
remain the integration coverage; no new live-agent or multi-item fixture was added.

Cancellation retains the candidate and prevents waiting preparation from starting
again automatically. A new explicit **Update & resolve** request can reauthorize
the same saved candidate; repeated requests for active work still reuse the same
operation. Failed preparation similarly accepts a new explicit retry without
throwing away an already assigned resolution item.

Interactive **Changes from conflict resolution** compares the retained previous
task copy with the current task copy, including uncommitted edits. It labels both
copies and the incorporated target revision; the final project comparison remains
the primary integration diff. Reads stay restricted to captured task paths.
