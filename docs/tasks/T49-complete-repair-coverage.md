# T49 — Preserve original requirements during final repair

Status: Not started
Priority: High
Depends on: current merged branch-run implementation
Size: M
Planning baseline: `4b6ed68`, September 14, 2026

## Outcome

A final review can request a correction to any originally authorized criterion,
including criterion 13 or later across a multi-item plan. The repair worker gets
the relevant requirements, and final readiness still covers the complete plan.
No requirement disappears to satisfy a per-item schema limit.

## Current evidence and files

Read [branch_completion.py](../../cheapos/branch_completion.py), especially
`_repair_item`, `authorization_run`, `finalize`, and `revise`; also read
[branch_runs.py](../../cheapos/branch_runs.py),
[branch_final.py](../../cheapos/branch_final.py), and
[branch_disagreement.py](../../cheapos/branch_disagreement.py).

The current trial repair applies `list(dict.fromkeys(criteria))[:12]` in both
construction and authorization validation. It therefore drops later criteria
from the repair item. Final manifests still enumerate original requirements;
do not claim that every original criterion has vanished from final review.
The defect is incomplete repair scope and instructions. Final manifests already
provide stable references such as `item-id:3`; reuse that identity.

## Work

1. Separate the immutable original requirement set from the small subset that
   needs correction. Identify requirements by original item ID and criterion
   position, not text alone: identical wording in two items is not one identity.
2. For automatic final-review repair, derive the subset from the validated
   structured defects and their original criterion references. Carry the exact
   references, text, source candidate/manifest, and supporting feedback into the
   repair record. Do not reduce this to the free-text feedback string.
3. A normal repair item still has 1–12 criteria. A finding against a late item
   must select that item's criteria rather than the first twelve in the plan.
   Keep all original requirements in the final verification/review manifest.
4. For operator-requested revisions, retain existing behavior when all original
   criteria fit. If a larger plan lacks unambiguous references, let the operator
   select the affected existing requirements in the revision preview. Explain
   the missing selection there; do not launch an incomplete correction or infer
   authorization for new requirements from arbitrary text.
5. Persist and validate the reference mapping as part of the exact amendment
   digest. Reject unknown/stale references, altered criterion text, changed
   checks, changed model policy, and increased limits. Preserve the original
   authorization projection and the current repair/item ceilings. If a requested
   correction cannot fit, offer a scoped revision before dispatch; do not silently
   partition it into extra authorized work or raise the allowance.
6. Handle saved legacy repairs explicitly. Retain their original records and
   receipts; never rewrite an approved contract in place or label an old clipped
   repair as complete coverage. A necessary replacement goes through the existing
   inspected revision flow. Document that compatibility behavior.

## Acceptance

- A five-item synthetic plan with at least 20 distinct criteria can repair a
  defect in its final criterion. The worker receives that exact requirement.
- The complete original requirement set remains in final readiness coverage;
  a failure outside the repaired subset still prevents final approval.
- Identical criterion text in separate items retains separate provenance.
- A one-item repair and a no-change reviewed outcome still work.
- Tampering with references, candidate identity, commands, or limits is rejected.
  Resume/restart does not duplicate amendments or renew repair allowances.
- A revision needing a criterion selection has a concrete next action, without
  executing a partial or broadened repair.

## Focused validation

Start with `python3 -B scripts/check.py --plan`. Add small in-memory tests for
reference selection and amendment validation. A 20-criterion dictionary is enough
to reproduce the clipping; do not run five real agents or create five Git histories
for it. Reuse relevant existing cases in `test_branch_completion.py`,
`test_branch_final.py`, `test_branch_authorization.py`, and `test_branch_ui.js`
where integration changes. Report actual selected cases and new-case timing.
Any new heavy test needs disclosure and operator acceptance first.

## Completion record

Record the implementation commit, reference/legacy format decision, focused
checks and timings, and any pending revision-preview browser check. Update the
trial report's claim that truncation preserves the repair contract, linking the
correction without rewriting the historical attempt as a different run.
