# T32 — Journaled automatic commits to the owned feature ref

**Depends on:** T30, T31. **Size:** L. **Result:** one approved item becomes one recoverable local feature-branch commit without touching the operator's index or files.

Read [BRANCH_RUNS.md](../archive/BRANCH_RUNS.md) and AGENTS.md first. Keep the existing manual commit endpoint intact. This is an internal controller operation, not a model tool.

## Read first

`cheapos/commits.py`, `Engine.commit_task/apply_commit`, workspace baseline advancement, T29's ownership mapping, T31 receipts, and failure/restart cases in `tests/test_commits.py`.

## Implementation

1. Create a dedicated branch-commit transaction using the run's authority and ready receipt. Require the active item/candidate, expected full feature parent, registered source/workspace identities, unchanged plan, and exact current evidence. Recheck ownership/default/protected/checked-out-ref rules immediately before updating the source ref.
2. Build a temporary index from the previous full source tree, apply only the current item's exact patch, and create the intended full tree. Preserve excluded/unmodified source entries. Do not stage the source index, use the filtered snapshot tree as the full source tree, or call `commits.apply_and_commit()` for this path.
3. Resolve the operator's Git identity under the existing repository policy before committing. Use a bounded plain-text message generated from the item outcome; reject invalid/control input. Do not embed prompts, raw logs, credentials, or giant model prose. Preserve current hook/signing behavior and document it, without quietly bypassing newly detected unsupported repository requirements.
4. Create a durable operation intent before advancing the feature ref. Store an operation ID, expected old tip, intended new commit/tree, exact patch/evidence references, private baseline transition, and stage. Advance only the owned ref with an expected-old-value check. A repeated operation may recognize its exact new commit, but must not adopt an arbitrary changed tip.
5. After the source ref succeeds, advance the private baseline with a recorded mapping to that exact content, then mark the item committed and publish its milestone once. Git and task JSON cannot commit atomically together: recovery must inspect both. If source succeeded but private advancement/save failed, finish the recorded operation before dispatching new work. Never delete/rewrite the successful source commit to conceal a partial save.
6. Support a safe internal committing transition while this run owns execution. Do not remove the global active-runtime guard from the manual path. The private candidate must be frozen against further worker writes while the operation runs. Serialize cheapoS writers by common repository/ref identity, including multiple source-worktree paths; revalidate external Git changes separately.
7. Record commit outcome distinctly from operator acceptance and merge. Do not call model-pool human-acceptance tracking just because autocommit succeeded. No empty commit for a reviewed no-change item. No push, branch deletion, rebase, amend, target update, or source checkout switch.

## Acceptance and validation

Use real Git fixtures. Assert source HEAD/index/dirty files are unchanged and the feature tree contains exactly expected changes plus preserved excluded entries. Cover two sequential patches and correct ancestry.

Inject failure before ref update, after ref update, after private baseline advancement, and before final task save. Retry/restart must yield one source commit and one milestone, with no lost patch or premature next item. Concurrent tip changes, a checked-out destination, changed candidate, and stale authority must fail safely. Keep manual commit/reconciliation tests passing.

## Completion record

Status: Done

Behavior delivered: `branch_commits.prepare/finish` journal immutable source/private commits, atomically verify ownership and compare-and-swap the feature ref, recover interrupted baseline advancement, and reject stale authority/candidates. Controller `commit_item` atomically records mapping/outcome and one operation-keyed milestone.

Acceptance evidence: Real source/index preservation, sequential ancestry, excluded-path collision refusal, ownership races, failures before/after ref updates and baseline advancement; final controller-save failure recovers the exact commit with one milestone and no human-acceptance record.

Commands and results: 8 branch transaction scenarios passed (initial 7: 64.220s, added race and sequential checks passed); 2 controller completion/recovery tests PASS (21.585s); all 26 existing manual commit tests PASS (121.548s).

Browser scenarios and results: Not required until T36/T40; transaction tests are required here.

Remaining limitations: Workers must remain frozen while the controller holds its commit transition. Source hooks/signing remain disabled under the existing manual Git policy; filters/sparse configurations are rejected. No publishing or target update occurs here.
