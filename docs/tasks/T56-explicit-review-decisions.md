# T56 — Require an explicit, consistent reviewer decision

Status: Not started
Priority: First — correctness
Depends on: current review implementation
Size: S
Planning baseline: `5a463b4`, September 14, 2026

## Outcome

A final review is approved only when the reviewer explicitly returns a valid
APPROVE decision with the required coverage. Missing fields, silence, positive
feedback, or an empty defect list cannot stand in for a decision.

## Confirmed defect and entry points

Read [branch_final.py](../../cheapos/branch_final.py), especially `_review` and
`validate`; also inspect the approval boundary in
[branch_review.py](../../cheapos/branch_review.py) and
[branch_evidence.py](../../cheapos/branch_evidence.py).

`_review` currently assigns APPROVE when both `decision` and `defects` are absent
or false-like. A pure in-memory reproduction supplied correct manifest/chunk/
criterion IDs and nonempty feedback, omitted `decision`, and received APPROVE.
No model, filesystem mutation, or Git fixture was needed. This is a confirmed
acceptance defect, not a claim inferred from the five-task trial's outcome.

## Work

1. Remove inferred approval. Validate the decision's type and allowed value before
   accepting the response. Missing, null, empty, boolean, unknown, or otherwise
   invalid decisions use the existing bounded correction path.
2. Keep any explicitly supported string case/whitespace normalization narrow.
   Do not infer a decision from feedback, missing defects, passing checks, or
   other fields. Preserve exact manifest, candidate and coverage checks.
3. Reject contradictory results, such as APPROVE with unresolved blocking defects.
   REQUEST_CHANGES still requires validated findings. Do not silently discard a
   rejection to make an envelope pass. T57 owns detailed finding normalization.
4. Apply consistent decision semantics to item and final review. A malformed
   response must not publish a ready receipt, advance an item, or make merge
   available. Preserve accumulated correction counts across Resume/restart.
5. Preserve existing histories; do not rewrite old stored approvals into claims
   of explicitly observed consent. Note any historical provenance limitation.
   This fix establishes the acceptance rule for new responses, not a retrospective
   requalification of earlier trial results.

## Acceptance

- Valid explicit APPROVE plus matching coverage succeeds; missing decisions never
  become APPROVE, including when feedback says the work looks good.
- Missing/null/empty/wrong-type/unknown decisions get corrective feedback and
  eventually pause under the existing correction allowance, without a receipt.
- A valid REQUEST_CHANGES retains its findings; contradictory approval is rejected.
- Stale coverage and changed candidate checks still fail independently of decision
  validation. Normal valid item/final review behavior remains intact.

## Focused validation and handoff

Start with `python3 -B scripts/check.py --plan`. Use a scripted reviewer and small
manifest dictionaries to exercise `_review` directly. Reuse affected existing
`test_branch_final.py` and `test_branch_review.py` cases; do not create a complete
branch/Git workflow to test a missing field. Report actual new-case timing and
get acceptance before introducing any heavy test. Commit the fix, record checks
and limitations here, and update TASKS.md. Do not run a live trial in this card.
