# T36 — One cheapoS conversation with visible branch progress

**Depends on:** T33, T35. **Size:** M. **Result:** every worker, test, reviewer, and commit step feels like part of cheapoS's response, with no unexplained silent task switching.

Read [BRANCH_RUNS.md](../archive/BRANCH_RUNS.md) and AGENTS.md first. Preserve the existing conversation layout and recent panel improvements.

## Read first

`CheapOSConversation` in `dist/guidance.js`, `stepMarkup/responseMarkup/renderComposer` in `dist/app.js`, stream rendering, scroll/detail state, and Node conversation tests. Verify actual helper names in the current source.

## Implementation

1. Extend the existing conversation projection with run/item IDs and stable event IDs. Nest execution under cheapoS replies; do not introduce separate floating Worker/Reviewer cards outside them or a mandatory second page. Keep Activity as optional detailed history.
2. Show a compact run summary: useful job title, feature branch, task X of N, current stage, and elapsed active time. Completed items show real outcomes and short SHAs. A task is not labeled completed merely because a commit event is pending or tests started.
3. Show real worker output, allowed provider reasoning/output, tool activity, live test output, reviewer activity, and recovery under expandable Details. Preserve model/role attribution there. Never fabricate “thinking,” generated progress percentages, passing tests, or independent review while waiting for a response.
4. After a successful item commit, append one natural-language milestone such as “CSV parser completed and committed as abc1234. Starting Markdown output, task 2 of 3.” Populate it from the durable controller receipt/next-item transition. No “What would you like to work on next?” until final integration; no intermediate Approve & commit buttons in this authorized mode.
5. Distinguish recoverable work from decisions: “Fixing a failing test,” “Addressing reviewer feedback,” “Waiting for a free route,” and a specific blocking reason. Pauses expose only the relevant Resume, scope approval, setup, or limits action. Avoid opening generic limits dialogs for unrelated failures.
6. Keep Pause beside the composer during work, tests, review, waiting, and finalization. Show Pausing while cancellation is in progress. Allow in-scope course corrections through the existing guidance path; never treat prose in the stream as an operator authorization amendment.
7. Preserve expanded Details, draft text, current task selection, and stable scroll anchors through polling. Return to the latest Chat output after switching from Activity/Changes/Checks as existing behavior specifies. While reading older messages, do not continually yank the view downward; provide a latest-output affordance.
8. Keep archive/Trash summaries accurate without leaking all item bodies into sidebar/list payloads. Keyboard focus, reduced motion, readable text, narrow layouts, and resizable/collapsible side panels must remain usable. Distinguish “committed to feature branch” from “merged to target” everywhere.

## Acceptance and validation

Use the three-item scripted run in an isolated browser. Expand worker Details, watch test output and review, observe one committed milestone followed by the next item, switch tabs and return, pause, resume, and refresh. Verify stable expansion/drafts and no duplicated milestones. Include a failed check/reviewer revision and a real blocker.

Add pure projection tests for duplicate delivery, restart, no-change items, wrong/stale SHAs, and finalizing versus ready/merged. Run frontend syntax/Node tests and the relevant streaming/HTTP integration. Record computer-use results, not only screenshots or string assertions.

## Completion record

Status: Done

Behavior delivered: One conversation contains worker/check/reviewer details and durable receipt-backed item milestones. Run status drives Pause through transient item approval/commit boundaries. Guidance retains the accepted scope and allowance.

Acceptance evidence: Pure projection tests reject stale/wrong receipts, deduplicate milestones, distinguish final/merged states, and cover actual rendering of new event shapes.

Commands and results: 88 Node tests passed, including branch UI and conversation regression coverage; app and branch-module syntax passed.

Browser scenarios and results: Expanded check/reviewer details survived Activity→Chat. Completed SHAs stayed visible through polling, pause/reload/resume. Narrow layout stayed within viewport; sidebar collapsed and restored with top control. No intermediate commit approval appeared.

Remaining limitations: Provider reasoning is displayed only when supplied. Completed runs explicitly offer a new chat rather than submitting unsupported guidance to a closed run.
