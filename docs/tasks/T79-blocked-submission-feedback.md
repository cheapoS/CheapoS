# T79 — Explain blocked submissions and make every Send path agree

Status: Deferred — implement when selected
Priority: Usability before concurrency
Depends on: Current composer, task creation/start, and saved-status presentation
Size: S
Evidence: Operator report, September 14, 2026, 4:11 PM; source inspected at `72532b4`.

## Problem and intended result

While an Unattended job was running, the operator tried an Interactive task.
Send was disabled. The operator reports that Enter put the prompt into a chat,
but no work started. The screenshot shows “Your message is saved and ready to
send” and another Send button. This must distinguish a saved request from an
executing or actually queued request. The screenshot's request about Trash is
example task content, not authorization to build deletion features here.

The current source blocks other busy chats in `renderComposer()` and again in
`sendChat()`. Task creation and `startTask()` are separate requests; `startTask()`
catches failures and only toasts them. `renderChat()` shows generic ready text
for a task with `status === 'ready'`. The Enter handler calls `sendChat()`
directly. Reproduce which entry path or timing creates the reported saved task;
do not claim the screenshot proves that the current `sendChat()` gate was absent.

## Implementation

1. Establish a common submission-availability decision for Send, Enter, the
   saved-task Send button, and relevant starter actions. Check it before clearing
   the draft or showing a user turn as submitted. Keep active-run guidance usable.
2. Explain the actual blocker near the composer: “Another task is running:
   [title]. This draft has not been sent.” Offer a link to that task. Do not
   automatically pause it, switch away from the draft, or call the request queued.
3. Handle a race where another task starts after the UI check. Preserve the
   server's rejection and the draft. If creation succeeded before start failed,
   retain that one saved task and show “Saved, not started” with the specific
   blocker and a retry action that starts the same task. Avoid duplicate tasks,
   duplicate user turns, silent returns, or a transient toast as the only notice.
4. When capacity becomes available, update controls through normal polling.
   Keep the draft/request intact and wait for the operator to send or retry;
   do not add automatic scheduling as an incidental behavior change.
5. Leave the current backend concurrency policy intact. T80 owns changing it.

## Acceptance and economical validation

- With A running, clicking Send and pressing Enter in B have equivalent results;
  no model call occurs for B and its text remains recoverable.
- An existing saved B explains why it has not started. Retrying after A ends
  starts B once. A lost start response is reconciled against saved state rather
  than creating a replacement task.
- Switching chats, reloading a saved task, keyboard use, and polling retain the
  correct blocker and draft. Sending guidance to A still works.
- Use controlled promises and a minimal API fixture for the creation/start race;
  small Node cases for shared availability/presentation. No real sleeps or live
  provider calls. Add focused HTTP coverage only if the response contract changes.
- Follow CONTRIBUTING.md; record timing of new cases. Propose any heavy test
  separately before adding it. Do not run the full suite for presentation alone.

Completion: Not implemented. Record behavior, selected checks, browser evidence,
remaining limitations, and new-test timing when this card is completed.
