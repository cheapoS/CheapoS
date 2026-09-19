# T39 — Explicit local integration and conversation close

**Depends on:** T32, T37, T38. **Size:** L. **Result:** one final operator approval integrates the exact reviewed branch locally and closes the job without another commit/review cycle.

Read [BRANCH_RUNS.md](../archive/BRANCH_RUNS.md) and AGENTS.md first. This first version supports fast-forward integration only. Push, PR creation, squash, rebase, and conflict-resolution merges are not part of the card.

## Read first

T37 preview/readiness, T32 durable journal, existing manual `prepare_commit/apply_commit` recovery, source Git configuration checks, `git-worktree` inventory, and [Git's merge documentation](https://git-scm.com/docs/git-merge).

## Implementation

1. Add an explicit final integration API requiring the fresh server preview ID and operator approval. Recheck run authority/state, source/common-Git identity, exact feature tip, target ref/tip, cumulative manifest, readiness/evidence, and absence of pending work. Neither initial run authorization nor reviewer APPROVE can call this on the operator's behalf.
2. Accept only a target that is an ancestor of the inspected feature tip (or already exactly equals it). Revalidate the complete branch change against the approved preview. Reject changed/diverged targets or unsupported configurations with saved work intact. Never choose another target, force a ref, auto-rebase, or create an unreviewed merge commit to get past the check.
3. Serialize cheapoS Git mutations for this common repository and record a durable integration intent before changes: operation ID, old target, feature tip, approved manifest/plan, destination checkout if any, and expected resulting tree. Use Git's locks/checks and verify state again before and after the operation. Do not assume an in-process lock prevents an external Git client from changing files or refs.
4. If the target is checked out in the selected source checkout, require that checkout/index to be clean and free of another Git operation. Perform a controlled fast-forward through Git so its files, index, and branch remain consistent. Keep current hook/signing/filter restrictions; suppress interactive editors/prompts. Never move only its ref underneath stale worktree files, auto-stash dirty edits, or reset/clean the operator's work.
5. If the target is not checked out anywhere, a conditional target ref advance can leave the operator's different checkout intact. If it is checked out in another operator worktree, return a clear unsupported-destination action for this first version rather than modifying an unselected directory. Reinspect worktree ownership at mutation; retain honest limits around concurrent external Git operations.
6. Journal recovery must distinguish not applied, applied but not saved, already integrated, and externally changed states. A network/UI retry or process restart cannot merge twice, create extra commits, or replay against a different target. Do not overwrite a changed destination while attempting recovery; retain the exact pending operation and explain the observed state.
7. Reuse valid final evidence rather than rerunning tests on approval. When the approved candidate/evidence actually changed, refuse stale approval and offer revalidation. A fast-forward adds the existing feature commits to the target; do not manufacture an extra “apply” commit.
8. On confirmed success, persist `merged`, target and resulting SHA, and the operator acceptance event separately from automatic branch-commit metrics. Show “Merged locally into <target> at <SHA>. What would you like to work on next?” New work gets a fresh run/branch contract. Keep the feature branch/history; no automatic cleanup or publishing.

## Acceptance and validation

Use real repositories to prove: checked-out clean target updates files/index/ref consistently; unchecked-out target advances without disturbing another checkout; dirty or externally checked-out target is left untouched; divergent/stale/changed-evidence approval fails; duplicate clicks and failures around the final save recover idempotently.

Browser-test the actual final button after T38, with one approval and no repeated tests/second commit dialog. Assert no remote was contacted and no push occurred. Run manual commit/reconciliation compatibility checks and the required complete integration gate for this behavior.

## Completion record

Status: Done

Behavior delivered: Explicit preview-bound local fast-forward preserves the original item commits. Durable merge intent supports exact recovery after target movement; failures retain a paused recovery state. Duplicate approval cannot create a new commit.

Acceptance evidence: Seven Git merge-helper tests plus completion integration validate clean checked-out/unchecked targets, dirty/diverged/stale state, explicit merge and crash recovery.

Commands and results: test_branch_merge.py: 7 passed in 55.805s; completion suite: 5 passed in 87.285s, plus saved-branch preview and strengthened crash recovery regressions passed.

Browser scenarios and results: Prompt run merged four feature commits; independent document run merged three. Target refs exactly matched approved feature tips and approval did not rerun checks. Completion displayed “Merged locally” and offered a new chat.

Remaining limitations: No force merge, rebase, conflict resolution, push or PR. Targets checked out in another worktree require separate integration planning.
