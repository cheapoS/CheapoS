# Operator-focused work details

September 14, 2026. The work disclosure previously rendered the task's entire
routing history before its thinking and actions. Candidate skips and request
IDs made useful progress difficult to find.

Chat now shows live output first. Running, failed, and changes-requested steps
open by default; an operator's explicit disclosure choice remains respected.
A collapsed running step shows the latest 240 characters of actual output,
limited to three visible lines. Waiting without output does not invent progress.

Within a step, routine consecutive file reads, outlines, searches, file lists,
and diff inspection share an expandable exploration group. Edits, narration,
checks, reviewer feedback, recoveries, and errors keep their chronological
positions. The latest recorded thinking opens initially. Failed checks and
review feedback open for reading; tool errors show their explanation directly.
The existing limit of 80 displayed events applies after diagnostic filtering.

Routing candidate lists and request records are available through a direct link
to Technical logs. They remain task-wide, retain existing partial-history and
unknown-served-model notices, and show newest selections/requests first. Nothing
in the persisted events, route policy, accounting, permissions, or controller
execution changes. This is a presentation filter, not deletion of diagnostics.

## Validation

- Changed-file selector: JavaScript syntax and 164 frontend cases passed;
  Node reported 110 ms for the selected suite. No Python suite was needed.
- Six new deterministic renderer cases took about 13 ms combined within that
  run. They cover routing noise, grouped exploration, failure/review evidence,
  live and absent output, interrupted thinking, and retained routing history.
  No live inference, real waits, or heavy workflow tests were introduced.
- Browser fixture used the real chat renderer, technical-log renderer, output
  helpers, and styles with disposable scripted state. Verified live chunks,
  collapsed previews, exploration across refresh/tab return, routing navigation,
  newest-first request inspection, honest waiting, reviewer thinking, command
  output, and visible errors/changes requested. At an effective 417 px viewport,
  document scroll width was 412 px, with no horizontal overflow; viewport reset.
- Fixture verification does not establish model quality or exercise backend
  dispatch. The running personal tasks and model settings were not changed.
