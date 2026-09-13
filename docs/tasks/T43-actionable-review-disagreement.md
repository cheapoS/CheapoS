# T43 — Concrete review disagreements before repair

Status: Not started
Depends on: T41
Size: M

## Outcome

When a reviewer disputes passing work, cheapoS carries a concrete defect claim
into repair, rather than treating an unsupported opinion as a reason to rewrite
correct code. Passing tests still do not prove every requirement is satisfied.

## Evidence and existing behavior

The [NVIDIA/Kiro medium trial](../trials/matrix/RESULTS.md) lost exact Decimal
precision after following a reviewer's incorrect float-conversion advice.
Final approval missed the resulting defect. The newer final-review prompt already
asks for a concrete failure; repeating that sentence is not this task's outcome.
Item and final review already bind decisions to candidates and support schema
correction. Extend those paths instead of creating a second reviewer engine.

Read `cheapos/branch_review.py`, `branch_final.py`, `branch_evidence.py`,
`branch_controller.py`, relevant review prompts in `engine.py`, and their tests.

## Work

1. Define a compact defect-evidence contract for Unattended revision feedback:
   relevant criterion, code/evidence location, expected versus observed behavior,
   and a concrete example/reproduction when executable. A static defect may use
   a precise code path and explanation; do not require every finding to run code.
2. For a claim contradicting supplied passing evidence, request its missing
   support through the existing correction path. Keep retries durable and bounded
   as appropriate for current normal/measurement semantics. Missing support must
   not become APPROVE, silently drop a finding, or authorize a repair by itself.
3. Send supported feedback and the current candidate/check context to the worker.
   Instruct it to demonstrate the claimed defect with a narrow regression or
   existing approved check before changing the disputed behavior. Preserve both
   original and new regression assertions after the fix.
4. Reproductions remain subject to existing command scopes. A reviewer-supplied
   command or Python snippet is not execution consent. Never execute arbitrary
   feedback, bypass test grants, or let the reviewer mutate files directly.
5. Present unsupported disagreement, supported repair, and unresolved review
   accurately in existing cheapoS activity. A persistent disagreement can pause
   with saved evidence; it must not oscillate through repeated identical edits.
6. Keep historical saved decisions readable. Document any additive fields and
   treat missing historical evidence as unavailable, not fabricated proof.

## Acceptance and focused scenarios

- A deterministic reviewer incorrectly claims Decimal `.2f` needs floats. The
  existing exact-value check stays intact; a concrete large-value probe disproves
  the suggested repair, and the controller does not accept unsupported approval
  or repeatedly request that precision-destroying edit.
- A real missing edge case produces supported feedback, a failing regression,
  a worker fix, current passing checks, and valid independent review.
- A concrete static defect remains actionable without demanding a shell command.
- Stale candidate evidence is rejected; repeated invalid feedback remains bounded
  across Resume/restart; an unapproved reproduction cannot execute.
- Existing valid review/commit and operator revision flows still work. Current
  check evidence is reused where valid, not rerun merely because review started.

## Validation

Use small deterministic provider sequences and temporary repositories. Start with
the affected cases in `test_branch_review.py`, `test_branch_final.py`, and
`test_branch_evidence.py`; include permission/recovery cases only where changed.
Inspect `scripts/check.py --plan` and explicitly document additional indirect
coverage. Reuse existing real repair coverage; new cases should use small
deterministic sequences rather than another expensive complete workflow. Disclose
any essential heavy case and obtain acceptance of its extra cost before adding
it. No full live matrix or full Python suite by default. If presentation changes,
run relevant Node/browser checks using disposable data.

## Completion record

Behavior delivered and feedback contract: pending
Acceptance evidence: pending
Commands/browser results: pending
Remaining limitations: pending

Update this card and TASKS.md; commit this repair separately from the exporter.
