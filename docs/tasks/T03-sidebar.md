# T03 — A manageable sidebar: menus, pin, archive, and full history

**Depends on:** T01, T02. **Size:** M. **Result:** chat history is organized and every chat is reachable.

## Read first

`dist/app.js` (`renderSidebar`, `openSearch`, task/project selection, polling), `dist/styles.css`, `dist/index.html`, and T01 list/metadata APIs.

## Implementation

1. Replace each monolithic task button with a task row containing a selection button and a separate overflow button. Do not nest interactive buttons. Make the menu visible on hover/focus and discoverable on touch.
2. Menu actions: Rename (reuse T02), Pin/Unpin, Archive. Only display implemented actions; Delete arrives in T05. Use accessible menu buttons and predictable Escape/outside-click behavior.
3. Keep pinned chats first within their project, then ordinary chats in a stable documented order. Do not reorder a row on every streamed token. Preserve selection and keyboard focus across polling.
4. Add project collapse/expand and Show more for older chats. The current twelve-row limit must become pagination/expansion, not inaccessible history. Keep collapsed/expanded state across refreshes; store only UI preferences, never secrets.
5. Add an Archived view/filter with Restore. Restore returns the chat to the main list without starting it. Archive of the selected idle chat chooses a sensible next chat or project home and preserves its draft.
6. For a running task offer `Pause & archive`, clearly naming both actions. Request stop, wait for actual idle status, then archive. Show progress; if stop fails or a commit is pending, keep the chat visible and show the error. Never hide a still-running task.
7. Search covers all applicable results, not only the rendered twelve rows. Label archived results and require restore before continuing them. Never automatically unarchive a chat just by inspecting it.

## Acceptance

Use a temporary fixture with at least 15 chats, two projects, pinned and archived entries, duplicate titles, and a live scripted task. Verify every chat is reachable, pin order is stable, group collapse survives polling, and archived chats restore after restart. Verify menu clicks do not accidentally select/send/start a task. Pause-and-archive must wait for shutdown and preserve saved work.

## Validation / limits

Add pure ordering/filter tests where useful. Browser-test mouse, keyboard, narrow layout, polling, search, and failure recovery. Do not alter source repositories, add permanent deletion, or introduce a new UI framework. Project removal is T06.

## Completion record

Status: Todo

- Behavior delivered: —
- Acceptance evidence: —
- Commands and results: —
- Browser scenarios and results: —
- Remaining limitations: —

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
