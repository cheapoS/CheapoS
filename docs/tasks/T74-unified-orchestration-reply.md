# T74 — Keep orchestration and live work inside one cheapoS reply

Status: Complete
Priority: High — coherent conversational workflow
Depends on: T68, T69, T70, T73; coordinate with T71/T72 UI integration
Size: M
Planning baseline: operator screenshot, September 14, 2026, 10:11 AM;
follow-up work inspected at `74fa83c` on `work/planner-reliability`

## Outcome and observed problem

The operator experiences cheapoS as one agent orchestrating the job. Each
operation has one owning reply containing its explanation, current status,
expandable live details, and eventual result or specific blocker.

The screenshot shows one planning operation in two disconnected places:

- An upper cheapoS reply says Working, includes `unknown: selected ...`, says
  it is choosing the next step, and contains a Preparing the next step card.
- A separate lower `cheapoS · Planning` block announces that the proposal is
  being prepared and shows a feature-branch name.

The operator cannot easily tell which block owns the work or which status to
watch. This task fixes the duplicated presentation, not the model workflow.
Inspect current integration first; some role and proposal UI fixes may already
be complete. Do not restart those cards or overwrite another agent's changes.

The follow-up screenshots at 10:15:07 and 10:15:16 show the same problem during
execution, plus unclear item ownership:

- The upper reply announces that independent review passed while the lower
  run summary still describes item 1 as reviewing. The screenshot alone does
  not establish a backend error; investigate presentation timing and ownership.
- When the lower summary advances to item 2, Style the restart button, the
  upper reply still mixes prior check/review results with a generic Working on
  your request row. It is unclear which result belongs to which item.
- A raw `reviewer: selected ...` sentence is presented as conversational text,
  and a second Tasks and committed outcomes section reports item 1 separately.

Resolve these with explicit item/phase ownership in the conversation, rather
than only merging two containers or changing the Planning label.

The completed-run screenshot at 5:32:08 adds the terminal-state case: the main
reply says Here's what I worked through and shows Earlier steps 41 plus repeated
review/check rows, while a detached lower section carries the actual outcome,
Merged locally into main, the commit, and the invitation to choose the next job.
The final outcome belongs in the main cheapoS reply, not in a separate footer
after a wall of workflow evidence. Repeated review rows must retain their item,
candidate, and item-versus-final-review context without implying duplicate work
when they represent distinct legitimate review stages.

## Intended interaction

One logical reply during planning:

```text
cheapoS · Planning

I'm preparing a plan for your request.

◌ Waiting for the planner's response · 27s                 Details >

You can add guidance while I work.
```

Details expands the actual live output inside this reply, with a clear
`Planner: <actual model>` label. When the proposal is ready, update the operation
to `Your plan is ready` with the existing Review plan action. A failure shows
T73's specific explanation in that same owning reply. Neither ready nor failed
state leaves a second stale Working/Planning announcement elsewhere.

Worker, checking, and reviewer phases use the same visual and interaction
pattern: a cheapoS explanation, an honest current action, inline Details, and
the supported result/action. Do not make them look like unrelated assistants
or independent floating job cards. Keep internal role separation intact.

## Read first

[app.js](../../dist/app.js) (conversation presentation, `renderChat`, live work
cards), [branch_ui.js](../../dist/branch_ui.js) (`renderStart`, `render`, proposal
and branch summary), [guidance.js](../../dist/guidance.js),
[branch_ui.css](../../dist/branch_ui.css), [styles.css](../../dist/styles.css),
[test_conversation.js](../../tests/test_conversation.js), and
[test_branch_ui.js](../../tests/test_branch_ui.js).
Reuse T68 role identity, T69 Plan view, T70 startup state, and T73 pause mapping.

## Implementation work

1. Trace all renderers that describe the same active operation. Give its
   presentation one owner and stable identity based on existing task/request/
   phase records. Integrate branch planning into the existing conversation
   renderer instead of appending a second planning conversation beneath it.
2. Keep the explanation, phase status, elapsed time where available, live
   details, and terminal result within that reply. Reuse a common presentation
   contract for planner, worker, checks, and reviewer so they cannot drift into
   different detached-card patterns on the next feature addition.
3. Use precise state labels: selecting a planner, waiting for its response,
   reading project context, preparing a proposal, running a recorded command,
   or reviewing saved work. Choose labels from actual state/events. Do not show
   both generic Working and a separate Planning announcement for the same work.
4. Keep meaningful motion and output visible: the current action and elapsed
   time remain in the reply; Details reveals streamed text/tool/check output
   nested under it. Preserve streaming, selected details, and expanded state
   through polling and role transitions. This is not permission to hide the
   entire workflow behind Technical logs or replace it with a static spinner.
5. Move routing implementation text out of the conversation body. A real model
   selection belongs in Details with Planner/Worker/Reviewer attribution, and
   the complete safe trace remains in Technical logs. Never render
   `unknown: selected ...` as cheapoS's conversational explanation. When model
   identity is not known yet, state that selection is pending rather than inventing
   an identity. Preserve the difference between requested and served identity.
6. Put feature-branch metadata in the Plan view or relevant expanded Details.
   Keep branch/target information visible in approval and merge controls where
   it affects a decision. A branch label is not a second conversational speaker.
7. Update an active operation in place when it completes, fails, or is paused.
   Remove stale spinners and expose the existing Review plan, approval, setup,
   or resume action as appropriate. Start still closes immediately under T70;
   its pending state must join the same task conversation without a duplicate
   optimistic reply when the server acknowledgement arrives.
8. Preserve chronology and task ownership. A new user instruction must not
   overwrite completed work or erase earlier replies. Guidance submitted while
   planning remains a user message in order; subsequent state belongs to the
   correct operation. New phases can become subsequent cheapoS replies when
   appropriate, but one phase must not be rendered twice. Do not merge the
   whole task history into one endlessly rewritten bubble.
9. Keep role identity and permission boundaries explicit in Details. A unified
   voice does not mean the worker reviewed its own patch or that planning
   approved a command. Rendering, tab selection, and expansion must not dispatch
   model calls, grant authorization, repeat tests, or synthesize progress events.
   No extra model call is needed to generate status narration.
10. Preserve accessible headings, focus, and current scroll behavior. Streaming
    should not repeatedly announce the entire transcript to assistive technology.
    Keep Pause near the composer and retain readable layout on narrow screens.
11. Scope every progress group to the relevant plan item and operation/attempt
    identity. During execution, include a concise active item title and progress
    such as `Item 2 of 3 · Style the restart button` inside the owning reply.
    Keep item 1's checks, independent review, and commit attached to item 1;
    they must not imply that item 2 has already passed those steps.
12. Reconcile review-complete, commit-pending, committed, and next-item transitions
    from a consistent saved state. Do not show the same item's current phase as
    both reviewing and review-complete in competing active summaries. If the
    next action is committing an approved item, name that action rather than
    falling back to Working or implying the whole run is finished.
13. Retain completed item summaries within the conversation, optionally collapsed
    under a named earlier item. Give Earlier steps groups meaningful item/phase
    context, not just a count spanning unrelated items. Use the Plan tab for the
    overall item/commit overview; avoid a duplicate detached Tasks and committed
    outcomes narrator beneath the live reply.
14. Keep result wording scoped to the evidence. A successful `git diff --check`
    is a whitespace check, not proof that behavioral tests passed or that the
    restart button works. Show what was actually checked, and distinguish item
    review approval from final-run approval. This task must not replace check
    commands or rewrite the accepted plan to improve the presentation.
15. Close the loop in the owning conversation reply. On actual completion or
    merge, lead with the concrete outcome: what changed, the supported check/
    review result, and whether it is committed on a feature branch or merged
    locally into the named target. Include the recorded commit/reference where
    useful and the existing invitation/action to start the next job. Never
    imply a remote push or merge that did not happen. Retain existing completed-
    run constraints: use the supported next-chat action where required instead
    of silently reopening authorization or editing a merged run.
16. Keep extensive earlier steps available beneath the conclusion with meaningful
    item/phase labels. Do not force operators through dozens of check/review rows
    to find out whether the run finished. Duration and measurement-mode metadata
    can live in expanded run details or Plan instead of a second narrator block.
    A concise final message should replace generic Here's what I worked through
    when a precise completed outcome exists; retained evidence remains inspectable.

## Acceptance and focused validation

- Reproduce the screenshot with a synthetic planning task: exactly one active
  cheapoS planning reply owns its text/status/live Details; no detached lower
  planning announcement or raw `unknown: selected` sentence remains.
- Selecting/waiting/streaming/plan-ready transitions update the same logical
  operation. Expanding Details shows actual role/model/output and stays open
  across polling. Review plan opens the existing inspected proposal.
- Planner failure uses T73's visible specific explanation within the reply;
  Pause and completion remove stale working indicators. Start pending and
  acknowledgement do not create two copies of the operation.
- Worker edits, command verification, reviewer response, and their results use
  the same owning-reply pattern. Active details are visibly nested rather than
  placed outside cheapoS's message. Independent roles remain distinguishable.
- Reproduce the three-item restart-button example using synthetic states: item
  1 implementation → checks → review approval → commit → item 2 styling. Each
  result keeps its item identity, the active title advances correctly, and no
  stale reviewing/Working summary competes with the actual next step. Item 1's
  check/review success must not appear as evidence that item 2 is verified.
- An item commit appears in its own completed reply/group and the Plan overview;
  there is no second detached cheapoS narrator. Earlier steps stay attributable
  after folding/unfolding, and whitespace-only evidence is not labeled as a
  passing behavioral test suite. Do not run an actual three-item workflow for
  this fixture; deterministic state transitions are sufficient for its logic.
- A saved merged-run fixture with 41 earlier steps renders the actual outcome
  and next-work action in its main cheapoS reply without a detached Merged locally
  narrator. Earlier evidence remains expandable and distinguishes item review
  from final review. A merely committed/unmerged fixture cannot claim a merge,
  and a local merge cannot claim a push. Use fixture records, not a new live run.
- Mid-operation guidance, task switching, reload, and returning from Plan or
  Technical logs preserve messages, operation identity, and expanded details.
  Chat's existing return-to-latest behavior still works without stealing scroll
  while the operator is reading older output.
- The requested tab order, persistent approved plan, inline failure reason,
  and immediate Start dismissal from earlier cards remain intact.
- Use small deterministic conversation/branch presentation fixtures and existing
  JS checks. In one isolated browser scenario, step through planner waiting,
  streaming, ready, Start, worker/check/reviewer output, and a specific failure
  using saved synthetic states or controlled responses. Verify actual visual
  containment and before/after output; markup assertions alone are insufficient.
- Reuse the T69–T73 browser fixture. No live inference, timed sleeps, full
  multi-item Git workflow, or new heavy regression suite. Measure any new cases,
  disclose any proposed heavy addition before adding it, and record browser gaps.

## Completion record

Completed in the T74 integration commit (recorded in Git history).

- `CheapOSConversation.branchBuild` owns planning, item, attempt, guidance and
  final-integration replies. Stable phase keys preserve expanded Details across
  polling; explicit item identity (including nested commit receipts) keeps prior
  checks/review/commits out of the next item. Current saved ready receipts select
  commit-pending presentation; intermediate selection names the next action.
- `CheapOSChatView` contains real streamed thinking/content and recorded command
  output, role/model identity, routing evidence and inline run controls.
  `branch_ui.render` now mounts controls inside the owning reply rather than
  appending another narrator. Plan retains overall tasks and branch metadata.
  Recorded questions and T73 specific failure actions remain visible.
- Completed receipts require matching item/run, completed stage and valid commit
  identity or a reviewed no-change outcome. Final integration names its actual
  target and feature tip. Whitespace checks, including reused checks, are labeled
  precisely. Missing historical model identity is unavailable, never guessed from
  today's selected provider.

Validation: 110 existing and extended conversation/branch/routing/guidance JS
cases passed in 0.090 seconds; syntax and diff checks passed. Nine added pure or
VM-render cases each measured below 2 ms. No model requests, workflow fixtures,
real-time sleeps, paid escalation, or authorization changes were introduced.

The shared isolated browser fixture verified one owning reply through planner
selection, waiting, real synthetic streaming, ready/Review plan, item checks,
independent review, commit and next-item transitions, a specific pause, and reload.
Expanded Details retained state and actual output remained nested. Browser review
caught and fixed stale waiting text and a stale live review label at commit. The
terminal fixture verifies merged outcome in the same owner; target/commit use the
actual saved receipt schema. These are synthetic presentation checks, not claims
that a live restart-button task or model qualification was run.
