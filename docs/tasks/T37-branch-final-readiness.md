# T37 — Combined verification, final review, and revisions

**Depends on:** T31, T33, T34. **Size:** L. **Result:** a finished item list becomes a genuinely reviewable branch, and feedback can reopen work without discarding its history.

Read [BRANCH_RUNS.md](../archive/BRANCH_RUNS.md) and AGENTS.md first. This card produces final readiness and preview data; T38 renders it and T39 performs the separate approved integration.

## Read first

T31 evidence receipts, T32 tree/baseline mapping, `Engine.checkpoint`, final/manual preview APIs, `verification.py`, diff limits, and reviewer read tools/raw check evidence.

## Implementation

1. Finalize only when every accepted item has a valid committed or reviewed no-change outcome, no transaction is pending, and the private working patch is empty. Recheck the owned feature tip and full commit chain against receipts. Missing/failed/skipped work cannot be hidden by a coordinator summary.
2. Compute the cumulative diff and manifest from the pinned original base to the current feature tip. Preserve the original base after each item commit. Include file status, byte/line counts, item/commit relationships, and exhaustive evidence references. Do not accidentally display only the last item's now-empty patch.
3. Run the agreed final integration command(s) against the final workspace contents. Reuse existing checks only with an explicit verified content/baseline mapping, matching commands and unchanged environment; a historical “tests passed” from an earlier item is insufficient. Do not rerun focused checks just because their stage changed, but changed relevant contents need current final evidence.
4. Obtain final independent review of the entire accepted plan, acceptance outcomes, cumulative change manifest, integration results, and uncertainties. Bound individual packets to existing review limits. For a large diff, use deterministic chunk IDs/content digests and explicit coverage records plus an overall synthesis decision. Every changed file/requirement must be accounted for; truncation or missing chunk approval cannot produce readiness. Respect existing request/time limits and report when the accepted scope exceeds them rather than silently dropping context.
5. If final checks fail or the reviewer requests changes, create a bounded repair item with links to the affected criteria/evidence and return to T33. Repair still uses the same branch and remaining budget, current checks/review, and T32 commits. Preserve the previous task/commit history. Broad new requirements require T30's operator amendment, not autonomous plan expansion.
6. On success, save a readiness record bound to plan revision, original base, feature tip/tree, current target ref/tip, manifest digest, check receipts/environment, and final review coverage/decision. Expose `ready_for_merge` only for an integration candidate supported by T39's fast-forward contract. Otherwise expose a clearly reviewed branch with a separate target-divergence/integration blocker.
7. Add read-only final preview preparation with a short-lived server-held approval token bound to that readiness and exact target/candidate. Refreshing a preview performs no inference, tests, commit, or merge. If evidence has become stale, return the specific needed revalidation action; don't start it silently from polling.
8. Handle operator “Request changes” after readiness. An in-scope correction invalidates the final preview, records the submitted request, and creates/continues repair work within remaining authority. Questions about existing results can be answered without invalidating content evidence or rerunning tests. Leaving the branch stops continuation and preserves it. Target changes invalidate target-bound approval even if feature code did not change.

## Acceptance and validation

Show a cumulative diff after three item commits with an empty current patch. Test overlapping file edits, a reviewed no-change item, final integration failure, final reviewer revision, and operator revision. Each changed final candidate must be revalidated, while read-only preview refresh and questions reuse valid evidence.

Exercise multi-chunk final review: omitted or changed chunks/criteria fail readiness. Test target drift and feature drift separately. Verify total budget includes finalization and repairs. Use real Git/checks and scripted reviews, with no source-target mutation.

## Completion record

Status: Done

Behavior delivered: Final checks bind to the clean private candidate; exhaustive cumulative manifest/chunk review covers every criterion. Bounded repair items retain original history and cumulative limits. Operator corrections use an inspected amendment.

Acceptance evidence: Actual final checks, multichunk coverage, overlapping commits/no-change history, stale target/environment, failed coverage and bounded amendments were validated.

Commands and results: test_branch_final.py: 6 passed in 80.425s after its event-emitting test fixture was updated. Completion tests and full gate recorded in T40.

Browser scenarios and results: Requested documentation correction produced a fourth reviewed commit and renewed readiness before final merge.

Remaining limitations: At most three repair items and twelve distinct original criteria per repair. Broader work needs a new scoped proposal. Oversized final review pauses explicitly rather than omitting content.
