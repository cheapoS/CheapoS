# T94 — Operator-controlled limits and autonomous completion

Status: **Planned — umbrella task**, September 18, 2026.

Canonical design: [Operator-owned limits and automatic recovery](../development/operator-limits-and-recovery.md).
Build on [T91 scoped settings](T91-settings-system.md) and
[AUTONOMOUS_WORKFLOW.md](../../AUTONOMOUS_WORKFLOW.md).

## Outcome

The operator chooses work budgets in a dedicated **Limits & recovery** section.
A task uses that saved policy consistently from planning through final review.
Ordinary agent/provider failures produce a useful authorized continuation.
Completing this task requires working recovery, not just clearer stop messages.

This is a tracking and integration task. Implement the six child cards as
separate, reviewable changes; do not duplicate their work in a seventh engine
rewrite. The cards contain the audit evidence needed to begin without access to
an operator's Desktop report or private task records.

## Ordered work

| Order | Task | Scope | Status |
|---|---|---|---|
| 1 | [T95 — Planning work policy](T95-planning-work-policy.md) | Capture and restore the selected policy before planning starts. | Planned |
| 2 | [T96 — Context-error recovery](T96-context-error-recovery.md) | Repair the oversized request before blaming or replacing the model. | Planned |
| 3 | [T97 — Provider recovery](T97-provider-recovery-consistency.md) | Consistent error classification and replacement-reviewer handoff. | Planned |
| 4 | [T98 — Durable strategy recovery](T98-durable-strategy-recovery.md) | Replace fixed repair stops with saved next-action decisions. | Planned |
| 5 | [T99 — Limits & recovery settings](T99-limits-settings-and-effective-budgets.md) | Scoped controls, migration, effective output budgets and user documentation. | Planned |
| 6 | [T100 — Large evidence and history](T100-large-evidence-and-history.md) | Verification capture, final-review paging and measured storage improvements. | Planned |

T95–T97 can be developed independently against their stated contracts. Land
those foundations before T98 integration; T99 builds on that behavior. T100 is
three ordered slices, not a single large rewrite. Its storage slice starts with
measurement, while verification/review improvements can proceed independently.

## Already covered; do not redo

Audit baseline: `49cbecbe6b1d42e9d3e488a81c504c2cccf273de`. Recheck current code
before implementation; later commits may already address a finding.

- `49cbecb` supplies structured syntax-edit rejections, immediate recovery and
  preserved indentation in fallback XML arguments.
- `21186a6` removes the 1,000-state progress-index saturation and projects repeated
  identical failed-edit exchanges while retaining full evidence. It does not
  implement the six cards above.
- `e4d2a53` records the limits design; it is documentation, not the settings UI.

Keep failure-specific syntax tracking. Global AST normalization is not a
replacement for progress tracking: comments, documentation and formatting can
be the actual requested change. Historical token savings were not established
by a controlled comparison; do not turn estimated savings into product claims.

## Shared implementation rules

Read [AGENTS.md](../../AGENTS.md) and [CONTRIBUTING.md](../../CONTRIBUTING.md).
Keep spending, permitted routes, pins, command grants, workspace boundaries,
independent review and exact candidate/check evidence intact. Account for every
dispatched retry and retain uncertain reservations. No handoff or Resume resets
usage or silently grants new authority.

Use the existing settings, accounting, continuation and executor owners.
Persist attempted strategies and selected continuation before dispatch. Do not
replay an identical failure indefinitely, add a larger hidden stop counter, or
require a coordinator for ordinary transport recovery. Waiting must reflect a
real scheduled availability check and remain cancellable.

Fresh installations may default to no cumulative work caps while retaining
free-only placement. Preserve existing app/project/chat choices on migration.
Only explicit operator changes expand saved authority. A chosen finite budget
or a genuine missing prerequisite is distinct from an engine failure.

## Parent acceptance

- [ ] T95–T100 complete, with per-slice implementation and validation recorded.
- [ ] Interactive and unattended work use the same saved limits and recovery
  meanings; planning, review and restart do not introduce hidden work ceilings.
- [ ] A deterministic failure-to-completion case reaches checked, independently
  reviewed work without an operator rescue message, setting change or Resume.
- [ ] A bounded case stops at the chosen budget, keeps its next action, and
  continues when the operator explicitly increases that budget without resetting
  counts. Spending, pins, grants and final merge approval still apply.
- [ ] Settings show scope, effective values and provenance. Existing chats do
  not change when defaults for future chats change.
- [ ] README/user documentation describes shipped behavior accurately.

Start validation with `python3 -B scripts/check.py --plan`. Reuse small scripted
providers, fake clocks and existing persistence/authorization fixtures. New
heavy workflows, long waits or full-suite checks need the repository's test-cost
justification and approval where required. Report new-test timing. Live trials
require explicit authorization and measurement mode; do not operate on private
saved tasks as test fixtures or restart the app as part of implementing a card.

## Handoff

Use the next child card as the implementation prompt, one task at a time. Update
its status and this checklist only after the behavior and relevant checks pass.
External development agents commit their own validated changes and tell the
operator; internal cheapoS workers leave Git operations to the controller.
