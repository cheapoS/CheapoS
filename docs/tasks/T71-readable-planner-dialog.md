# T71 — Widen the planner and improve proposal readability

Status: Implemented
Priority: High — readable planning and approval
Depends on: current planner/proposal dialog; coordinate with T69/T70
Size: S
Planning baseline: `db774c7`, September 14, 2026

## Outcome

The planner/proposal window is wide enough to read instructions and acceptance
criteria comfortably. Long plans remain navigable, and approval controls are
easy to find without reducing font size or hiding requirements.

## Read first

[branch_ui.js](../../dist/branch_ui.js) (`dialog`, proposal inspection),
[branch_ui.css](../../dist/branch_ui.css),
[styles.css](../../dist/styles.css) (shared modal rules), and
[test_branch_ui.js](../../tests/test_branch_ui.js).

## Implementation work

1. Give planning/proposal dialogs a dedicated responsive width instead of the
   narrow shared-modal default. Start around 1000–1100 CSS pixels on a roomy
   desktop, constrained to the viewport with roughly 24px margins. Tune after
   visual inspection; small screens should use available width, not overflow.
2. Preserve readable body text (target the app's normal 16px body scale), clear
   line spacing, and hierarchy between item titles, instructions, criteria,
   check commands, and metadata. Do not fit more content by shrinking text.
3. Use a bounded scrolling body and accessible close/footer controls. A long
   proposal should not strand Start at an unreachable position or hide content
   under a sticky footer. Keep focus visible while tabbing and scrolling.
4. Wrap long paths and text; command/code blocks may scroll horizontally within
   their own region. The whole dialog and page must not develop horizontal
   overflow. Preserve every acceptance criterion and required check.
5. Scope CSS to planning dialogs so Connections, permissions, and unrelated
   confirmation windows do not unexpectedly become oversized. Coordinate with
   T69's Plan view to share useful content styles without coupling it to a modal.
6. Preserve the immediate Start behavior from T70 when integrated. Visual changes
   must not add another approval step or alter the accepted proposal contract.

## Acceptance and focused validation

- Inspect a long synthetic multi-item proposal at a 1440px desktop viewport,
  a 1024px laptop viewport, and about 390px narrow viewport. Also inspect desktop
  at 200% zoom. Text and controls remain readable, reachable, and unclipped.
- Long paths/check commands cannot force page-level horizontal scrolling.
- Keyboard focus, close, content scrolling, and Start work with the expanded
  layout. Unrelated modal layouts retain their existing dimensions.
- Reuse T69/T70's browser fixture; no model calls or Python full suite. Use
  existing JS/syntax checks for changed UI code and visual verification for CSS.
  Do not add a heavy screenshot pipeline for this adjustment. Record viewports,
  screenshots if useful, checks, and any new-test timing in the completion record.

## Completion record

Dedicated planning-only responsive1080px layout,16px text, sticky header/actions, wrapping paths and bounded scrolling. Unrelated modal widths unchanged.

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
escaping/redaction and old-record limitations. Browser live-event reading-anchor
updates are implemented but not separately exercised with mid-scroll injection.
