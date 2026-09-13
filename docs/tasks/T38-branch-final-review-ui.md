# T38 — Cumulative diff and one final decision

**Depends on:** T36, T37. **Size:** M. **Result:** the operator reviews the complete finished branch in Chat and can approve, request changes, or leave it saved.

Read [BRANCH_RUNS.md](../../BRANCH_RUNS.md) and AGENTS.md first. T39 implements merge execution; do not ship an enabled button backed by a placeholder success response.

## Read first

Existing commit-decision markup/actions, diff rendering/escaping, conversation completion helpers, T37 final-preview schema, and browser/Node tests for revisions and stale previews.

## Implementation

1. Render a final cheapoS response summarizing completed items, total files changed, actual required check results, reviewer outcome, and feature/target branches. Say “Ready for your review,” not “Merged” or “Accepted.” Link each item to its outcome and committed SHA in collapsible details.
2. Present the cumulative diff from T37, organized by file with accessible expansion/pagination for large content. Show additions/deletions and explicitly represent unsupported preview types. Fetch omitted content from the pinned candidate, not the current moving branch name. Never render a truncated diff as the full patch.
3. Offer three actions: “Approve & merge locally” when T39 is available and eligible, “Request changes,” and “Leave on feature branch.” Keep final approval in the same conversation rather than adding another generic Apply & commit screen. Until merge execution lands, show an honest unavailable state and retain inspection/revision actions.
4. Display exactly what approval will do: integrate the inspected feature tip into the named local target; no push or PR. Keep the candidate/target SHA accessible in Details. No second confirmation for the same fresh final approval. Bind submission to the current server proposal token, disable duplicate submission, and recover uncertain responses through server transaction status.
5. Request changes should focus/retain the composer and submit the operator's guidance to the same run. Show resumed work and append new commits/updated final review. Read-only questions remain conversational. Leave preserves history and branch with an explicit way to reopen review; it does not delete work.
6. Handle stale target/candidate, changed evidence, exhausted limits, missing Git identity, and unsupported integration clearly. “Refresh preview” only refreshes; “Recheck changes” explicitly returns to verification when required. Do not offer an inert Refresh & commit loop or imply repeated clicks can resolve a diverged branch.
7. Preserve keyboard access, focus after errors, Details state, drafts, readable layout, and the latest Chat position. Keep manual single-patch approval behavior unchanged. Normal per-item automatic commits must never show the final merge control early.

## Acceptance and validation

In an isolated browser fixture, complete three items and inspect changes from both the first and last commit. Ask a question, request a correction, observe a new reviewed commit, and see the cumulative preview update. Test Leave/reopen, stale preview, target divergence, narrow layout, refresh, keyboard operation, and no duplicate submissions.

Run UI projection and API integration tests. At this card's handoff, clearly record whether T39 is installed; do not claim merge succeeded if only a disabled future action exists. Final actual merge UI is verified in T39/T40.

## Completion record

Status: Done

Behavior delivered: Final review shows the cumulative base-to-feature diff, per-file manifest, checks/reviewer evidence and exact target. Only a current explicit preview can authorize merge; blocked or revoked runs keep a read-only diff.

Acceptance evidence: Backend coverage tests bind preview to readiness/target and reject stale/cross-task approval. UI projection and actual renderer tests pass.

Commands and results: Final frontend gate: 88 Node tests passed; syntax passed.

Browser scenarios and results: Prompt and document browser flows displayed all seven changed files, including the first CSV module and last CLI/document edits. Revision invalidated prior readiness; Leave retained an inspectable diff with merge disabled.

Remaining limitations: Local-only integration; unsupported/dirty/divergent targets show a blocker. Saved terminal reviews expose only read-only actions.
