# Update branch & recheck

When the target branch advances during a task, open **Review changes** and choose **Update branch & recheck**. This explicitly approves combining the inspected target into the saved task branch. It does not merge into the target or push anything.

The controller requires completed items, an idle task, a clean private copy, unchanged branch ownership and a current preview. It creates a merge commit that preserves both histories and journals the update before changing the private copy or feature ref. An interrupted update can be retried using the same control. Existing item receipts and usage remain saved; previous final approval is archived. The combined candidate must pass the authorized final checks and independent review before **Approve & merge locally** becomes available.

Conflicts stop preparation without modifying either checkout or branch. Uncommitted edits and unrelated branch movement are retained and reported, never automatically reset or stashed. Conflicting changes currently require explicit resolution; this action does not ask a model to guess a conflict resolution.

Regression coverage uses small controller/receipt and UI tests. Real divergent-branch, interrupted-update, and final-review smoke checks reuse existing disposable Git fixtures during development rather than adding a slow recurring agent workflow.
