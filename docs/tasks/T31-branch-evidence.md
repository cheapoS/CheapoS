# T31 — Exact candidate evidence and independent review gate

**Depends on:** T28, T29. **Size:** M. **Result:** automatic commit eligibility is a controller decision about actual verified work, never a model's completion claim.

Read [BRANCH_RUNS.md](../archive/BRANCH_RUNS.md) and AGENTS.md first. This card produces an evidence receipt; T32 consumes it to commit.

## Read first

`cheapos/verification.py`, `Engine.checks/checkpoint/reviewed_patch`, reviewer tools/decisions, `cheapos/environment.py`, and verification/review-workflow tests. Inspect the current manual takeover path carefully.

## Implementation

1. Introduce an explicit candidate identity for an item: run/plan/item revision, expected feature parent, private baseline, current patch/content identity, workspace generation, and selected check specifications. Reuse the current runner/dependency/config identity rather than inventing a looser patch-only gate.
2. Support the item's finite set of required checks. Existing tasks with one `check_command` remain compatible. Each record must retain its own command and evidence identity; avoid mutating a shared command field merely to make another record appear current. Missing environment, timeout, truncated/incomplete execution, or changed inputs cannot pass.
3. A passing check may be reused only for the matching candidate and command/environment. If tests modify relevant files, invalidate the candidate and inspect/rerun as appropriate. Do not require every historical check to have passed: an initial failure followed by a current passing result is expected repair behavior.
4. Construct an item review packet with the item's instructions/acceptance criteria, relevant overall plan/dependencies, exact diff, current check results, and uncertainties. Parse the existing structured reviewer decision. Require a distinct worker/reviewer model identity under the available gateway identity rules, and record both. A same-model local second request must not be called independent or enable this mode silently.
5. Tie APPROVE to that candidate and plan revision. REQUEST_CHANGES returns actionable feedback for repair. TAKE_OVER keeps its explicit authorization behavior and never becomes an automatic-commit shortcut: an implementing reviewer must receive independent review from a different eligible model before autocommit. Do not reuse the manual `completed` exception.
6. Produce an immutable ready receipt identifying the exact patch, candidate, required check records, reviewer decision/model, and criteria outcomes. At commit time the controller must revalidate against actual files, plan, and parent. A no-change item requires evidence that its criteria are already satisfied and a reviewer decision bound to current contents; record `satisfied_without_change`, not an empty successful patch by default.
7. Keep historical receipts after commits. A baseline advance does not invalidate the fact that an earlier candidate was verified, but that receipt cannot authorize a new patch. T32 may record an exact content/tree mapping; do not overwrite old evidence with the new baseline hash.

## Acceptance and validation

- Valid checks plus independent APPROVE yield a ready receipt; test failure, wrong model, missing criteria, TAKE_OVER, or mere status `completed` does not.
- File, command, runner, dependencies, baseline, parent, or plan changes invalidate eligibility.
- An unchanged checked candidate reuses evidence; a repaired candidate requires fresh evidence.
- A legitimately already-satisfied item completes without an empty commit; an unimplemented empty patch cannot complete.
- Existing manual verification/review behavior remains intact.

Use scripted providers, actual temporary-file edits, and relevant verification/review regressions. No source commits or UI in this card.

## Completion record

Status: Done

Behavior delivered: Exact per-item candidates, per-command execution identities, independent named-model review, complete criterion outcomes, immutable JSON receipts, and actual Engine checkpoint integration. No-change items require the same evidence gate.

Acceptance evidence: Actual temporary subprocess checks; stale file/plan/parent/runner identities rejected; old failed checks do not prevent repaired candidates; same-model and incomplete-criteria approvals rejected; unchanged checks reused.

Commands and results: `test_branch_evidence.py` 6 PASS; `test_branch_review.py` 2 PASS (5.946s); existing `test_verification.py` 7 PASS (9.083s).

Browser scenarios and results: Not required for this backend-only card.

Remaining limitations: Item packets exceeding 30,000 characters pause explicitly for smaller planned items. The final cumulative chunk review belongs to T37. Takeover cannot bypass independent review.
