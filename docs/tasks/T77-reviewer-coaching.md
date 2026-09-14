# T77 — Automatic reviewer reassessment before a routine stall

Status: Complete, September 14, 2026
Depends on: T60, T73, T74
Size: S

## Problem

An unattended item reviewer could repeat unchanged reads or unusable decisions
and hit the progress guard without a focused recovery instruction. The outer
engine converted its specific reason into a generic “Work stopped making
progress” banner and told the operator to invent a correction.

## Implementation

- After two identical review observations, two invalid decisions, or before the
  ordinary final allowed review request, cheapoS supplies one focused nudge.
  It references the exact current candidate, original criteria, supplied checks,
  repair findings and worker counterevidence. The reviewer must identify the
  remaining blocker and make a valid decision or read genuinely missing context.
- The instruction explicitly prohibits automatic approval, weakening checks,
  repeating unchanged reads, reopening resolved findings without evidence, or
  treating source/model claims as instructions. Existing receipt validation
  still decides whether a model's approval can be accepted.
- The nudge is saved before dispatch, bound to pending review/candidate identity,
  and reused across restart. It does not reset work/spending limits or add
  requests beyond the existing review allowance. Measurement behavior remains.
- Chat shows “Reassessing the review” with an inspectable “Helping the reviewer
  reach a decision” event inside the owning cheapoS reply. The event remains in
  Details after a pause; it never counts as successful review.
- Exhaustion distinguishes repeated evidence, repeated failed tools, no usable
  review action, invalid decisions, and the review request limit. A typed saved
  diagnostic survives the inner engine wrapper and public serialization. It
  describes whether coaching was attempted and offers inspection instead of a
  generic request for the operator to write routine guidance.

## Scope and limits

This change addresses unattended **item review**, not every kind of agent stall.
It does not add a reviewer-model handoff, override disputed requirements, resume
personal tasks automatically, reset exhausted historical attempts, or grant new
command/model authority. Existing final-review correction and worker recovery
mechanisms remain unchanged. A failed reassessment can still need inspection or
another reviewer; coaching is an attempted recovery, not a guarantee of success.

## Validation

Focused Python coverage: 32 distinct cases across existing branch review,
disagreement, dispute-ledger, and pause modules. The initial 31-case run passed
in 21.751s; almost all that time came from existing real repository/check cases.
After adding the failed-tool diagnostic case, the affected disagreement/pause
modules passed all 21 cases in 0.090s. No unchanged integration suite was repeated.
The 140 frontend cases passed in 107.526ms, plus changed JS syntax checks.

Five new deterministic Python cases use tiny in-memory state and mocks, without
Git, subprocesses, inference or sleeps; each measured below 2ms. One new JS case
covers visible coaching, preserved Details and absence of false approval.
An existing pure invalid-decision case also asserts that coaching and its exact
exhaustion reason were saved. No heavy test was introduced.

Computer use exercised a disposable HTTP fixture with the actual frontend.
Active coaching appeared inside the review, a typed saved stop displayed the
specific failure and prior recovery, and Details retained the coaching event.
No live provider calls or personal task data were used as fixtures.

The deterministic recovery case converged after two repeated reads and one
coached response through the normal receipt path. Separate cases ignored the
nudge and stopped after three requests; serializing/reloading that saved state
could not renew the same exhausted attempts. This is regression evidence,
not a claim about real-model success rate.
