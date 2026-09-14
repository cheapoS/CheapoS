# T57 — Carry validated findings through repair and write guards

Status: Not started
Priority: Second — correctness
Depends on: T56
Size: S/M
Planning baseline: `5a463b4`, September 14, 2026

## Outcome

The exact findings accepted by validation are the findings stored, shown to the
worker, used to identify repeated disputes, and enforced before implementation
edits. No later stage falls back to unchecked raw reviewer arguments.

## Confirmed defect and entry points

Read [branch_disagreement.py](../../cheapos/branch_disagreement.py) (`validate`,
`repair`, `attach`, `before_write`),
[branch_review.py](../../cheapos/branch_review.py), and
[branch_final.py](../../cheapos/branch_final.py). Check the request packet in
[engine.py](../../cheapos/engine.py) that carries `review_repair` forward.

`validate` returns cleaned findings, but item and final callers currently discard
that return value. A pure reproduction used an accepted legacy finding with a
nonempty reproduction and missing `kind`. Validation classified it as executable;
the stored raw finding still lacked `kind`, so `before_write` skipped the failing-
check requirement. Supplying the normalized finding correctly blocked the edit.

## Work

1. Make validated canonical findings the only input to repair construction,
   persistence, worker packets, dispute tracking, and executable-defect guards.
   Capture and use the validator's return value at every acceptance boundary.
2. Define supported legacy aliases explicitly. Validate types before string
   operations; reject ambiguous/conflicting aliases, unsupported kinds, invalid
   locations and references. Do not invent a file/line or downgrade an ambiguous
   executable claim to static solely because a reproduction is missing.
3. If an accepted legacy form is unambiguous, normalize it once and enforce the
   same rules as the canonical form. Raw output may remain bounded diagnostic
   evidence, but must not regain authority downstream.
4. Make prompts/schema agree with their review context: item review currently
   uses item criterion text, whereas final review uses manifest requirement IDs.
   Do not tell the item reviewer to return `1:1` if its schema requires exact
   criterion text. T49 owns mapping repairs back to original requirement IDs.
5. Validate saved pending findings before using them after restart. For an
   unrecognizable legacy record, retain work and explain the missing validation;
   do not silently disable the guard, fabricate evidence, or rewrite immutable
   historical receipts. Document this compatibility behavior.

## Acceptance

- The confirmed missing-kind reproduction either normalizes to an executable
  finding that requires evidence, or is rejected before repair; it never bypasses
  the write guard.
- Both item and final callers preserve the canonical list through save/load and
  the worker's next packet. Accepted aliases do not change enforcement.
- Invalid types and conflicting fields produce controlled correction feedback,
  not accidental exceptions or accepted defaults.
- Static findings remain supported with precise evidence. Executable findings
  still need a reproduction and the existing check-evidence conditions.
- Item/final instructions agree with their actual criterion schema.

## Focused validation and handoff

Start with the selector plan. Use tiny dictionary-based cases in
`test_branch_disagreement.py` and focused caller tests with scripted requests.
The reproduction needs no Engine runtime, network, repository, or real check
command. Reuse existing integration coverage for persisted repair behavior.
Report new-case timings, supported normalization/legacy decisions, and the commit.
Any new heavy test requires advance disclosure and acceptance.
