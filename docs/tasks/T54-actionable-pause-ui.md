# T54 — Explain pauses inside the conversation with a useful next action

Status: Implemented — browser acceptance pending
Priority: Medium
Depends on: T53, T60
Size: M
Planning baseline: `4b6ed68`, September 14, 2026

## Outcome

cheapoS explains a pause as the orchestrator: what stopped, what is saved, and
what the operator can do next. The explanation appears beside the current work
in Chat, with expandable details. Operators do not have to interpret internal
codes, inspect a server log, or repeatedly press a Resume button that cannot help.

## Current evidence and files

Read [branch_ui.js](../../dist/branch_ui.js) (`presentation`, rendering, and action
handlers), [app.js](../../dist/app.js), [guidance.js](../../dist/guidance.js),
[branch_ui.css](../../dist/branch_ui.css), and the public record from T53.

Branch presentation currently chooses `task.error || run.pause_reason` and often
offers generic Resume/Recheck. Preserve the existing unified conversation, visible
Pause control, operator drafts, chronological activity, and review/merge controls.
This is a focused pause experience, not a layout redesign.

## Work

1. Add a pure presentation mapper from structured pause evidence to a short
   headline, explanation, primary action, and optional Details. Reuse it wherever
   the branch pause is shown so Chat and Activity do not give contradictory advice.
2. Describe known state precisely. For example: “I couldn't finish the review:
   the provider reported its daily quota exhausted. Your saved edits are waiting
   for review.” Do not claim changes exist, checks passed, or a commit completed
   without the corresponding evidence.
3. Map actions to the actual blocker using existing handlers:

   | Cause | Appropriate action |
   | --- | --- |
   | Operator pause / restart | Resume saved work; use saved-operation recovery if an integration was interrupted |
   | Provider quota | Models, or existing retry/wait only when eligible; show a reset time only if known |
   | Missing executable/setup | Open task-environment setup and re-check |
   | New command grant | Review the exact requested permission |
   | Exhausted allowance | Review the relevant limit, retaining already counted usage |
   | Essential clarification | Focus the reply composer with the saved question visible |
   | Branch/authority change | Inspect the existing conflict or authorization flow |
   | Malformed output/repeated work | Show the specific failure and the supported correction/retry action |
   | Repeated review dispute | Show the disputed requirement, latest findings and counterevidence, and the controller-supported next action |

4. Details should identify the affected item, worker/reviewer stage, safe model
   label, and retained diagnostic reference. Do not show raw tracebacks or secret
   provider payloads. Escape all text, including filenames and error strings.
5. Preserve expanded Details, draft text, and scroll behavior across polling and
   tab switches. Keep Pause near the composer while a request is active. A
   paused run must not retain a “working” animation from the previous request.
6. Disable an action while it is submitting, surface its failure inline, and use
   the existing idempotent server behavior. Refresh or opening Details must not
   retry a provider, renew an allowance, authorize commands, or merge work.
7. Keep legacy-state fallback readable without presenting an unverified cause.
   Preserve the post-merge invitation to choose the next job.

## Acceptance

- An operator can identify cause and next action from Chat for each listed state.
  Reviewer quota is not mislabeled as a code defect or a request for requirements.
- A restart and a true unanswered question lead to different explanations/actions.
- Historical task states without structured details remain usable.
- Repeated polling, switching Chat/Activity, and action errors preserve draft,
  expanded details, and understandable progress. Text is safely escaped.
- No extra model call, test run, or approval is triggered by rendering the UI.

## Focused validation and handoff

Start with the selector plan. Add small synthetic cases to `test_branch_ui.js`
and affected guidance tests; reuse existing HTTP handlers. No Python full suite.
Use computer use on an isolated fixture server for at least reviewer quota,
restart, and a clarification, including refresh and one action-error path. This
is a focused browser check, not a new heavy agent/Git regression test. If browser
access fails, record the exact missing scenarios as pending; Node checks are not
a visual pass. Report new-case timing, browser evidence, and commit.


## Implementation record — September 14, 2026

Added a pure pause mapper and escaped conversation banner with retained Details and existing action handlers. Reviewer quota goes to Models, restart to saved Resume, questions to the composer, setup/permission to their existing controls, and unknown/dispute evidence to Activity. Generic Resume is suppressed for typed blockers; no saved edits/checks/commits are invented.

Validation: 74 focused branch/guidance Node cases passed in about 0.095 seconds, including three new pure pause cases. Syntax checks passed. Browser acceptance remains pending for reviewer quota, restart, clarification, refresh/tab retention and one action-error path: prior CUA loopback navigation returned `net::ERR_BLOCKED_BY_CLIENT`; in-app browser was unavailable and native inspection returned no state before interruption. No bypass or browser-pass claim was made.
