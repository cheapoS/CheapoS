# T69 — Keep the approved plan visible in its own task tab

Status: Implemented
Priority: High — operator orientation
Depends on: current persisted plan and authorization contract
Size: M
Planning baseline: `db774c7`, September 14, 2026

## Outcome

After inspecting a proposal, approving it, and clicking Start, the operator can
open Plan at any time to read what was approved and follow progress. The plan
does not disappear with the planner dialog or require reopening an approval flow.

Required order:

- No available plan: **Chat → Changes → Activity → Tests → Technical logs**.
- Available plan: **Chat → Changes → Plan → Activity → Tests → Technical logs**.

Use **Changes** (plural). Rename the visible Checks tab to **Tests** as requested;
the existing internal `tests` view and broader verification data remain valid.
Do not create a blank Plan tab for ordinary chats or for a placeholder planning
item before an actual proposal exists.
T72 owns the Technical logs view. This card implements the other tabs and their
relative order; keep Technical logs last when T72 is integrated, rather than
adding a nonfunctional placeholder. Chat and Activity stay chronological.

## Read first

[index.html](../../dist/index.html) (tablist/view panels),
[app.js](../../dist/app.js) (view switching, rendering, scroll),
[branch_ui.js](../../dist/branch_ui.js) (proposal rendering and run state),
[branch_ui.css](../../dist/branch_ui.css),
[branch_runs.py](../../cheapos/branch_runs.py), and
[test_branch_ui.js](../../tests/test_branch_ui.js).

## Implementation work

1. Render Plan from the persisted task/run data. Before Start it may show the
   ready proposal as a draft; after authorization label the approved scope
   clearly. Do not depend on a transient `proposal` variable or dialog DOM.
2. Show the job summary, ordered item titles, acceptance criteria, required
   checks, final checks, relevant branch/limits, and current item/status. Keep
   long instructions and supporting details expandable so progress is scannable.
3. Preserve the original approved plan separately from status updates and
   explicitly authorized repair/revision items. Never rewrite approved scope
   based on model narration. Show revisions with their provenance, not as if
   they were in the original proposal.
4. Make the tab available while running, paused, awaiting review, completed,
   and after reload/reopening the task. If older records lack a complete plan,
   state the limitation instead of inventing one or showing the wrong task's plan.
5. Keep this view read-only. Use existing chat/revision paths for changes that
   require a new proposal or authorization; viewing Plan must not restart work.
6. Update tab order, accessible labels, focus/keyboard behavior, active state,
   and narrow-window overflow. Preserve the user's selected view during polling.
   Switching to a task without Plan falls back to Chat if Plan was selected.
7. Preserve Chat's return-to-latest behavior and avoid resetting Plan expansion
   or scroll during ordinary progress updates. No provider calls on tab clicks.

## Acceptance and focused validation

- Chat/Changes/[Plan]/Activity/Tests render in that order with one active panel;
  after T72 integration both complete tab orders above include Technical logs last.
- Approved content survives Start, status updates, task switches, and reload.
- Progress matches saved item state; draft, approved, and revision content are
  distinguishable. No view action changes authorization or dispatches work.
- Use deterministic saved-plan JS fixtures and an isolated browser task. Check
  expanded items, long content, keyboard navigation, and ordinary-chat fallback.
  Reuse this fixture for T70/T71. No full agent run; record browser evidence and
  new-case timings. Update this card/TASKS.md and commit scoped changes.

## Completion record

Implemented persistent read-only Plan from saved authorization contract (draft uses saved proposal), original scope separate from revision provenance and live status. Tabs reordered with keyboard navigation, per-task expansion/scroll retention. Focused Node: 19 cases, 68.8 ms total; two new pure cases 0.24 ms. Browser verification shared with T70–T72 remains pending until their integration.
