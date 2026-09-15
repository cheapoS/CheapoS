# Update branch & recheck

When the target branch advances during a task, open **Review changes** and choose **Update branch & recheck**. This explicitly approves combining the inspected target into the saved task branch. It does not merge into the target or push anything.

The controller requires completed items, an idle task, a clean private copy, unchanged branch ownership and a current preview. It creates a merge commit that preserves both histories and journals the update before changing the private copy or feature ref. An interrupted update can be retried using the same control. Existing item receipts and usage remain saved; previous final approval is archived. The combined candidate must pass the authorized final checks and independent review before **Approve & merge locally** becomes available.

Conflicts stop preparation without modifying either checkout or branch. Uncommitted edits and unrelated branch movement are retained and reported, never automatically reset or stashed. The separate Resolve conflicts & recheck action assigns those conflicts to the agents with captured evidence.

Regression coverage uses small controller/receipt and UI tests. Real divergent-branch, interrupted-update, and final-review smoke checks reuse existing disposable Git fixtures during development rather than adding a slow recurring agent workflow.

## Agent-assisted conflicts

If the update detects conflicts, **Resolve conflicts & recheck** assigns an explicit new item to the existing worker and reviewer. The item retains the original task, usage, model policy, spending allowance and verification commands. Agents can read frozen base/task/target/suggested versions with `read_merge_context`; this does not grant arbitrary access to the source checkout. The suggested versions contain Git’s automatic combination and any unresolved markers. Agents must incorporate incoming nonconflicting changes as well as resolve conflicts.

After the resolution passes item checks and independent review, the controller records the merge ancestry without changing the reviewed tree. Final checks and review run before human merge approval. The controller journals this operation for recovery after interruption. An incompatible product choice uses the existing evidence-backed clarification flow; routine code conflicts remain agent work. Binary or oversized conflict evidence is reported explicitly instead of silently omitted.
