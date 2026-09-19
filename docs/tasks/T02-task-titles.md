# T02 — Useful task titles and one clear header

**Depends on:** T01. **Size:** M. **Result:** the operator immediately knows which task is open and can rename it.

## Read first

`dist/index.html` topbar/task heading, `dist/app.js` (`renderTask`, `renderHome`, `selectTask`, `setView`), `dist/guidance.js`, `cheapos/engine.py` task creation/follow-ups, and T01's metadata/presentation contract.

## Implementation

1. Replace the generic `project / Chat` breadcrumb with the effective task title in the primary header. Show the project as a secondary folder label. Keep one prominent title, the status, and useful view tabs; remove duplicate stacked task titles.
2. Preserve a home/new-chat header when no task is selected. Browser tab title should reflect the task with a cheapoS suffix. Switches between tasks, projects, and home must clear stale titles.
3. Provide an accessible Rename action from the title area. Use a small dialog prefilled with the current name. Enter saves, Escape cancels, errors stay inline, and focus returns predictably. Send plain text through T01's API; render with textContent/escaping.
4. Add deterministic automatic naming, without another model request. Prefer an explicit custom title. Otherwise select the first substantive user request: ignore a small, documented exact greeting-only set such as `hi`, `hello`, `hey`, `hi gemma`; do not label every short question a greeting. Normalize whitespace, use the first meaningful nonempty line/sentence, trim at a word boundary to a readable length (about 72 characters), and fall back to `New chat`.
5. A greeting-only chat gains its automatic title when substantive work arrives. Once a substantive automatic title exists, ordinary follow-ups do not keep renaming the chat. Manual names are never overwritten; resetting to automatic uses the original substantive request. Use stored requests to support old greeting chats without running a bulk migration.
6. Do not mutate task prompts, conversation history, commit messages, model context, or execution status just to name a chat. Keep the title policy in a small independently testable helper.

## Acceptance

- `hi` then `Create a CSV converter with tests` gets a meaningful title; `Why?` remains a valid substantive request.
- Custom `CSV tools` survives follow-ups, worker saves, reload, and restart.
- Long prompts, multiline prompts, emoji, quotes, and HTML-looking text display safely and without layout overflow.
- Header shows the same title as the sidebar; project identity remains discoverable.
- Pause stays beside the composer; fallback Pause remains reachable on other views.
- Rename/cancel/error flows work with keyboard only and at a narrow viewport; current draft and scroll position remain intact.

## Validation / limits

Add title-policy regressions to an appropriate Python or JS helper test, depending on ownership. Use a local scripted task to exercise rename during streaming. No LLM title generation, sidebar archive/delete controls, or rewording of stored user requests.

## Completion record

Status: Done

- Behavior delivered: Deterministic first-substantive-request names, manual rename/reset, a single primary task header, secondary project identity, and metadata-aware polling.
- Acceptance evidence: Greeting/short-question/Unicode/long-prompt policy tests; manual names survive follow-ups and restart; requests remain unchanged.
- Commands and results: 2 title tests and 5 metadata tests passed; 60 JavaScript tests and app syntax check passed; diff whitespace check passed. T01 integration ran 304 tests: 278 passed in sandbox; 26 socket-binding errors resolved by passing HTTP (26 tests) and gateway module reruns with loopback access.
- Browser scenarios and results: Enter saves; whitespace errors stay inline; Escape cancels and returns focus; literal HTML-looking/emoji names render safely; reload retains name; in-session draft survives rename. Renamed an active scripted task through checks/review; worker events and title survived. Checked header/dialog at 390px and reset viewport.
- Remaining limitations: Long names truncate visually with full title available; composer drafts retain existing session-only persistence.

Before implementing, read [TASKS.md](../archive/TASKS.md) for the shared contract. Update this record and the matching board row when complete.
