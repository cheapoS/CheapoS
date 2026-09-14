# T75 — Submit directly and approve Unattended work in one screen

Status: Complete
Priority: High — remove duplicate setup and approval friction
Depends on: T65, T69, T70, T74 (completed foundations)
Size: M
Planning baseline: `397e36f` on main, September 14, 2026

## Outcome and operator decision

Unattended work feels like: describe the job, inspect cheapoS's proposed approach,
then authorize it. There is one mandatory review-and-start screen after planning,
not a setup dialog before planning followed by another approval window.

The accepted flow is:

1. Select Unattended in the composer. Enter a prompt, select a project document,
   or provide both, then send.
2. cheapoS prepares the proposal visibly in Chat with the existing inline
   progress, streamed Details, guidance, and Pause behavior.
3. Review & start shows the plan and execution settings together. The operator
   can adjust them within this flow and inspect the resulting validated proposal.
4. Start immediately closes the window and returns to the visibly starting
   conversation. The approved plan remains available in Plan.

Planning itself uses the already configured planner and authorized planning
allowance. The final approval authorizes execution; it cannot retroactively
authorize planning charges or silently enlarge the planning allowance.

## Current behavior and entry points

In [branch_ui.js](../../dist/branch_ui.js), `requestDialog` first discovers the
project's branch defaults, then opens Start unattended work. Its form repeats
the prompt/document and asks for committed base, local target, feature branch,
and measurement mode. Submitting that form starts `/branch-runs/plan-start`;
a later proposal dialog asks for execution approval. Remove the first mandatory
form while preserving its useful inputs and validation.

Read the submission/proposal helpers in that file, [app.js](../../dist/app.js)
(composer and task selection), [branch_ui.css](../../dist/branch_ui.css),
[branch_controller.py](../../cheapos/branch_controller.py) (`plan`, `prepare`,
`authorize`, `planning_message`), [branch_authorization.py](../../cheapos/branch_authorization.py),
[server.py](../../cheapos/server.py), and the completed T65/T69/T70/T74 cards.
Use [unattended-runs.md](../unattended-runs.md) for the existing user-facing flow.

## Implementation work

1. Submit the composer prompt/document directly to planning after lightweight
   validation and existing project/default discovery. Preserve one planning
   request identity, duplicate-submit protection, drafts, task selection, and
   visible pending/error state. Enter and the send button must use the same path.
2. Use the open project, existing main/default-branch discovery, current generated
   feature-name mechanism, selected models, and saved preferences. Do not change
   the checkout or guess that uncommitted project edits are included. Make the
   actual source/base and snapshot behavior visible in the final review.
3. Keep the optional project-document input reachable before submission because
   the planner needs its contents. Do not make the operator re-enter a prompt or
   document already supplied in the composer. Prompt-only, document-only, and
   combined requests all remain supported.
4. Put optional pre-planning overrides in a clearly labeled composer expansion
   or existing settings affordance. They must not become a second mandatory
   setup screen. When project/model setup or an essential input is genuinely
   missing, explain it inline with the existing relevant action; preserve the
   draft and avoid beginning an invalid model request.
5. Keep planning within its current authorized model/access/spending policy and
   existing accounting. Free-only remains free-only. Optional execution changes
   on the later review screen must not retroactively change planning limits or
   authorize further planner requests under a newly inferred budget.
6. Use one roomy Review & start screen after the proposal is ready. Reuse the
   T71 layout and organize it around readable plan items/acceptance criteria,
   followed by concise execution settings with expandable advanced fields:

   | Information | Expected behavior |
   | --- | --- |
   | Job and selected document | Show captured inputs; allow a scoped planning revision without losing context |
   | Ordered plan and checks | Show item scope, acceptance criteria, required checks, and final checks |
   | Project and branches | Show committed base, local target, and feature branch; retain protected-ref and conflict validation |
   | Models | Show the actual planner used and selected execution roles; explain automatic placement when a worker is not yet selected |
   | Allowances | Show execution limits and planning usage already accounted; preserve model/access policy and explicit measurement semantics |
   | Test permissions | Show the exact proposed check scopes and any existing grants; Start authorizes only the represented scopes |

7. Support edits without restarting the operator from the original setup form.
   Reuse the planning conversation for scope changes and the proposal-preparation
   path for execution-setting changes. Regenerate/revalidate when changes affect
   the captured source, scope, commands, models, limits, or branch contract.
   Show pending validation and disable Start until the displayed proposal is
   current. Preserve unchanged inputs and show specific field-level errors.
8. Bind the final Start to the exact displayed validated proposal and its
   approval identity. Editing a field must invalidate the previous Start token;
   never send new values with stale authorization or bypass existing validation.
   A corrected proposal stays in the same review flow, with no extra generic
   Are you sure modal after Start.
9. Preserve measurement mode as an explicit choice, never an inferred default
   used to evade limits. A live qualification request must still follow AGENTS.md
   and request measurement before planning. Explain any resulting mode/allowance
   changes in the reviewed contract; do not silently renew existing usage.
10. Retain T70's synchronous dismissal, visible Starting state, idempotent server
    handling, and unknown-outcome reconciliation. Rejected or stale starts return
    actionable errors to the correct chat without losing the captured proposal.
    Retain T74's single owning reply and T69's persistent Plan tab after Start.
11. Preserve permission boundaries after Start: genuinely new commands or changed
    scopes may still require approval. One initial approval is not a blanket
    grant for arbitrary shell commands, installations, paid fallback, merge, or
    push. Keep current final-review/merge and saved-startup recovery behavior.
12. Update the work-mode documentation and any onboarding help to match the
    reduced flow. Remove stale instructions for the first Start dialog and
    distinguish Send/prepare plan from Start/authorize execution in labels.

## Acceptance and focused validation

- With an open project and configured models, selecting Unattended and sending
  the composer content starts visible planning without a setup popup. Both Enter
  and the send button behave consistently; double submission creates one request.
- Prompt/document inputs and saved defaults reach the planner correctly. Missing
  required setup appears inline, retains the draft, and does not dispatch invalid
  requests or require repeating inputs that are already available.
- Exactly one mandatory Review & start screen presents the complete proposal and
  execution settings after planning. Optional advanced settings do not block the
  normal path, and the actual planner model is not confused with future choices.
- Changing a branch, scope, check command, or allowance produces a current
  validated proposal before Start becomes available. Stale approval identities
  cannot authorize a different contract. Validation errors preserve the draft.
- Start immediately returns to Chat with honest pending progress; delayed,
  failed, unknown, and repeated responses preserve the existing recovery rules.
  The approved content is still readable in Plan after start/reload.
- Planning usage is retained, free-only does not become paid, measurement is
  explicit, and test grants remain bound to the inspected command scopes.
  Viewing/editing/reopening the review does not silently start execution.
- Interactive mode and existing planning follow-ups retain their behavior.
  Branch metadata remains available for review even though the first popup is gone.

Start with the change-scoped selector plan. Use small JS submission/state cases,
controlled pending promises, and existing proposal/authorization fixtures for
changed backend paths. Reuse the isolated browser fixture from T69–T74 to check
direct Send, live planning, the single review screen, an edited-field error,
Start dismissal, and the saved Plan view. No live model requests are necessary.
Do not introduce real sleeps, a new full multi-item agent/Git workflow, or a heavy
browser suite by default. Measure new-case costs and follow the disclosure rule
before proposing anything heavy. Record any unverified browser scenarios.

## Completion record

Implemented on `work/single-review-start`; included in the implementation commit that closes this card.

- Send prepares directly in Chat. Project document stays beside the composer;
  base/target/feature overrides and explicit measurement moved into optional
  Planning settings. Saved configured models and limits remain the defaults.
- Review & start combines captured source, plan, checks, model identity, spent
  planning usage, branches and execution allowances. Edits disable Start;
  validation replaces the proposal identity in the same screen. Late responses
  cannot authorize edits made while validation was pending.
- Scope discussion reuses the same chat and captured document/private snapshot.
  Restoring the original planning allowance prevents execution edits from
  funding more planning. Usage and reservations remain cumulative.
- Focused validation: 133 frontend cases passed in 95.737 ms; existing proposal
  reprepare cases passed in 10.245 s; two existing asynchronous planning HTTP
  cases passed in 3.383 s. Three new pure planning-allowance cases passed in
  0.001 s. No live inference or new heavyweight fixture was used.

Browser verification used the existing disposable app fixture with synthetic
responses, without provider requests or personal tasks. Combined prompt/document
Send reached planning directly with discovered defaults and one request ID.
Review & start remained one dialog through an invalid-target error and corrected
validation. The invalid value was retained and Start stayed disabled; corrected
validation produced a new token. Start dismissed immediately to Chat and a
synthetic rejected response remained visible with recovery guidance. The saved
Draft Plan retained its prompt, tasks and checks after reload. The desktop
six-item review remained readable with its sticky Start action. Successful Start
followed by an approved Plan reload was not repeated in this browser fixture;
existing T69/T70 saved-plan/start coverage remains in place.

The three new JS payload/validation cases use pure data and controlled promises;
the selected frontend suite completes in under 0.1 seconds. No new browser suite,
real sleeps, or full agent-run fixture was added.
