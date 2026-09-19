# T29 — Committed-base snapshot and owned feature branch

**Depends on:** T28. **Size:** L. **Result:** a run has an isolated execution copy and a new source-repository feature ref without changing the operator's checkout.

Read [BRANCH_RUNS.md](../archive/BRANCH_RUNS.md) and AGENTS.md first. T30 will expose authorized creation; this card provides validated controller-only primitives and real Git fixtures.

## Read first

`Workspace.snapshot/path/changes/patch`, snapshot exclusion constants, `commits.source_git/source_state/prepare`, `cheapos/project_permissions.py`, and existing commit/reconciliation fixtures. Relevant Git references: [ls-tree](https://git-scm.com/docs/git-ls-tree), [read-tree](https://git-scm.com/docs/git-read-tree), and the ref/worktree references in the milestone document.

## Implementation

1. Add a snapshot-from-commit path, preferably in `cheapos/branch_workspace.py` plus a small Workspace helper. Resolve an explicit base ref to a commit during proposal preparation; capture its object ID. Materialize eligible blobs from that commit, not from source working files or the live index. Retain existing manual snapshots unchanged.
2. Apply all existing file/size/path exclusions before writing. Preserve allowed executable modes. Reject path traversal and avoid following symlinks, symlink parents, or submodules into other repositories. Record skipped tracked paths without exposing contents. Do not copy `.git` or use an alternate object database accessible to model tools. Preserve current 5,000-file/100-MB snapshot bounds.
3. Store an explicit mapping: canonical source/common-Git identity, pinned full base tree/SHA, private snapshot baseline SHA, and feature ref/tip. Skipped source paths must later remain in the full source tree unchanged; the filtered snapshot is not a replacement source tree.
4. Validate new branch names through Git, require an exact local branch ref, reject symbolic/ambiguous refs and the selected target/default/protected refs, and check all linked worktrees. Feature refs must be newly created or already owned by this same run during idempotent recovery. Refuse unrelated existing branches, even when their content matches.
5. Separate read-only preparation from creation. Revalidate the prepared project, base, name availability, and authorization inputs immediately before mutation. Create a new ref conditionally only if absent. Use an operation intent plus a Git-side ownership marker created in the same ref transaction (for example, a private `refs/cheapos/runs/<run-id>` marker) so recovery can distinguish this run's creation from somebody else's same-name/same-SHA branch. A JSON intent and matching tip alone are insufficient ownership proof. Never use force, checkout, switch, reset, stash, or source-index staging.
6. Keep the workspace under the task's registered private data directory, preferably the existing `tasks/<id>/workspace` shape. Reject destinations inside the source or overlapping another run. Do not automatically delete a ref/workspace after an ambiguous failure; retain enough state to reconcile ownership safely. No garbage-collection feature in this card.
7. Document unsupported repository configurations using the existing filters/sparse/submodule checks as a baseline. Do not silently run content filters/hooks/signing while materializing a snapshot. Unsupported projects should get a specific preparation error, not weakened exclusion behavior.

## Acceptance and validation

Use real temporary repositories, including a linked operator worktree. Capture source HEAD, index tree, tracked file bytes, untracked files, and unrelated refs before and after creation.

- Dirty tracked, staged, and untracked source edits remain untouched and absent from the committed-base snapshot.
- The feature ref starts at the pinned base; the private snapshot contains only eligible files with correct modes.
- A tracked excluded file stays present in the source tree and is never exposed in the private copy.
- Invalid/protected/existing names, changed base during proposal, source replacement, symlinks, oversize input, and partial-creation retries behave explicitly.
- No current operator checkout switches branches. Manual snapshot regression tests still pass.

Do not wire automatic execution, merge, or the public Start action yet. Record the exported helper contract for T30/T32.

## Completion record

Status: Done

Behavior delivered: `branch_workspace.prepare/materialize/create/validate_owned` provide read-only source preparation, private committed-byte materialization, owned feature creation, and exact source/private identity checks. Feature and ownership marker creation share a conditional Git transaction.

Acceptance evidence: Dirty source/index/untracked bytes preserved; binary/executable/excluded entries handled; linked worktrees, identity replacement, branch collisions, partial retries, changed prepared copies and configured protected refs checked.

Commands and results: `test_branch_workspace.py` 11 PASS (35.430s); existing `test_engine.py -k snapshot` 1 PASS.

Browser scenarios and results: Not required for this backend-only card.

Remaining limitations: Filters, sparse/assume-unchanged and shallow repositories are unsupported. Symlinks/submodules/oversize entries stay excluded and are recorded. Partial private-copy failures retain artifacts and pause for inspection. `materialize` may create the private preview before authorization, with no source object/ref mutation; T30 binds consent to that exact copy.
