# T72 — Expose Technical logs as the last tab, newest first

Status: Implemented
Priority: High — diagnose stopped work without digging
Depends on: T69, T73
Size: S/M
Planning baseline: `db774c7`, September 14, 2026

## Outcome and current behavior

The operator can open Technical logs directly from the task tabs and immediately
see the newest saved events and why work stopped. They should not need to scroll
through Activity and find a nested disclosure to reach the technical details.
T73 must already show the actual failure in Chat's primary stop banner. This
view adds supporting evidence; it must not become a prerequisite for understanding
the basic problem or required next action.

At the baseline, `renderActivity` builds a technical event list from
`task.events.map(...)` and nests it in the Activity view. Promote that existing
task-scoped information into its own view. This is not a request to expose raw
daemon files, environment variables, or unfiltered provider request/response logs.

The final orders are:

- No plan: **Chat → Changes → Activity → Tests → Technical logs**.
- Plan available: **Chat → Changes → Plan → Activity → Tests → Technical logs**.

Only Technical logs use reverse chronological order: last log first. Chat and
the human-readable Activity timeline retain chronological order.

## Read first

[app.js](../../dist/app.js) (`renderActivity`, `eventDetail`, `renderView`,
`setView`), [index.html](../../dist/index.html) (tabs/panels),
[styles.css](../../dist/styles.css),
[server.py](../../cheapos/server.py) (`public_task`),
[branch_pause.py](../../cheapos/branch_pause.py), and
[test_branch_pause_ui.js](../../tests/test_branch_pause_ui.js).
Coordinate with T69's view lifecycle and T68's planner identity/trace work.

## Implementation work

1. Add a directly accessible Technical logs tab and dedicated panel for both
   planned and ordinary tasks. Keep it last regardless of whether Plan appears.
   Move the nested technical list out of Activity; an optional shortcut there
   may select the new tab, but do not retain two competing log viewers.
2. Render a reversed copy of the saved events or use a nonmutating sorted view.
   Use their durable sequence/append order so equal timestamps still have stable
   newest-first ordering. Never call an in-place `reverse()`/`sort()` on the
   shared `task.events` array or alter server storage chronology.
3. On first opening the tab, show the newest entry at the top. Each row should
   include available timestamp, event kind/title, role/model, and a concise
   result. Expandable details must expose the saved diagnostic fields relevant
   to that event: safe error text/code, stage, route failure reason, command
   exit status, request identity, or bounded output where available.
4. Make the latest saved stop/failure cause and supported next action prominent
   at the top when the task needs attention. Reuse the structured pause/error
   contract; newer housekeeping events must not hide why work stopped. If a
   useful technical detail exists, provide an obvious expansion or direct event
   link. Do not replace precise recorded causes with an invented diagnosis.
5. Add a View technical logs action to applicable stop/error banners so one click
   reaches the relevant record. Retain existing Resume/settings/setup actions;
   viewing logs does not authorize a retry, execute commands, or dismiss failure.
6. Live updates must preserve open details and the operator's reading position.
   When reading the newest entries at the top, new events may stay in view;
   when inspecting older entries, avoid jumping on every poll and provide a
   small new-entries/return-to-latest control. Do not steal focus or switch tabs.
7. Escape all content and reuse existing secret filtering and output bounds.
   Do not expose headers, keys, full raw provider payloads, or new server-wide
   log endpoints. If saved history is truncated or diagnostic data is missing,
   show that limitation. Never fabricate a missing traceback or error code.
8. Preserve accessible tab/panel labels, keyboard navigation, per-task state,
   and a helpful empty state. Switching tasks must not leave another task's
   error expanded or displayed. Archived tasks may still inspect their logs.

## Acceptance and focused validation

- Technical logs is the last tab with and without Plan. The technical list is
  reachable directly and is no longer buried inside Activity.
- Events with IDs 1, 2, 3 display as 3, 2, 1, including equal timestamps;
  the original saved array and Chat/Activity ordering remain unchanged.
- A fixture containing a specific provider error or check failure followed by
  a generic pause/housekeeping event exposes the concrete saved cause at the top.
  The error banner shortcut reaches that diagnostic without scrolling to the end.
- New events preserve expanded details and older-event reading position, with
  a clear way back to the latest entry. Reload and task switching are correct.
- Secret-like fields stay filtered, HTML-looking text renders safely, and
  missing/truncated history is described honestly.
- Use small JS event fixtures and the same isolated browser fixture as T69–T71.
  Simulate event updates deterministically; no sleeps, new agent runs, or live
  inference. Record browser results and timings for any new cases. Update this
  card/TASKS.md and commit the scoped changes.

## Completion record

Direct Technical logs tab last with immutable reverse append order, safe bounded field projection, specific canonical stop summary and Chat shortcut. Reading anchor, open details and keyboard focus persist across progress renders; return-to-latest control; Activity remains chronological.

Change-scoped check.py selected zero Python modules; syntax/diff checks and121
existing/extended Node cases passed in102.6ms. Four added controlled promise/log
cases are individually below1ms; no heavy fixtures, sleeps or inference.

Browser: isolated synthetic HTTP fixture exercised full real app. Verified Plan
persistence, keyboard tab navigation, stale Start → Chat rejection, specific
failure shortcut, newest-first equal-timestamp events and expanded error fields.
Measured CSS viewport widths1440/1024/390 produced modal widths1080/976/366 with
16px text and no horizontal overflow. Screenshots showed readable text and
reachable sticky Start/Close controls.720CSS desktop-equivalent layout exercised;
literal200% browser zoom remains unverified. Pure fixtures cover event ordering,
escaping/redaction and old-record limitations. Browser live-event injection with 52 saved events verified that expanded older
entry 20 keeps the same viewport position after a new event arrives. Return to
latest reaches the top and newest entry. This revealed and fixed native scroll
anchoring and a control-insertion offset; no test sleeps or inference were used.
