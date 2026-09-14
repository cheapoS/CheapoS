# T43 — Concrete review disagreements before repair

Status: Done
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

Behavior delivered and feedback contract:

- New Unattended `REQUEST_CHANGES` decisions need additive `defects` (1–8):
  `criterion`, `location`, `expected`, `observed`, `kind` (`static` or
  `executable`), `support`, and `reproduction`. Executable claims require a
  concrete reproduction; static claims may leave it empty. Item claims bind to
  the exact candidate; final claims bind to the manifest and assigned coverage.
  No historical receipt or decision is rewritten or given fabricated evidence.
- Missing support returns through existing reviewer correction messages. Three
  unsupported attempts persist under `branch_run.review_disagreements`; Resume
  cannot renew them, including in measurement mode. Identical actionable item
  claims are limited to three repair handoffs under `repair_claims`; final
  amendments retain their existing three-repair limit.
- Runtime items retain `review_repair`: original claim, candidate ID, bound check
  records, reproduction-first instruction, and check baseline. This survives
  restart and is supplied to the worker. Final amendments retain it before the
  amendment is saved. Activity distinguishes unsupported feedback from an
  actionable claim; neither is described as independently proven fact.
- For executable claims, the file-tool gate permits conventional test-file edits
  but blocks implementation edits until an actual nontruncated failed check on
  current inputs is recorded after the claim. Failed required checks release
  this gate too. A passing counterprobe can return to independent checkpoint
  without rewriting correct implementation. Read tools and normal approval
  paths remain available; reviewer commands and snippets never execute directly.

Acceptance evidence:

- Tiny deterministic item/final provider sequences reject unsupported claims,
  retain attempts across serialized restart, preserve actionable static claims,
  and prevent endless identical repairs. A Decimal large-value probe verifies
  `.2f` preserves `9007199254740993.01` while float conversion loses it; the
  unsupported rewrite never reaches the worker.
- The executable gate rejects stale or passing records and accepts a current
  actual failure. Existing command-consent coverage is extended with an immediate
  declined reviewer-style probe: no subprocess runs. Existing three-item and CSV
  end-to-end fixtures still exercise actual failure, repair, independent review,
  commits, and explicit local integration.

Commands/browser results:

- Inspected `python3 -B scripts/check.py --plan` and explicit changed-file plan.
  The engine import fanout selects 56 modules, so focused indirect coverage was
  chosen instead of running the broad selection.
- Ran `scripts/dev_tests.py` for `test_branch_disagreement`, `test_branch_review`,
  `test_branch_final`, `test_branch_evidence`, `test_branch_completion`,
  `test_branch_execution`, `test_branch_end_to_end`, `test_permissions`, and
  `test_branch_exclusions`: 49 distinct tests pass. An initial missing limit in
  the new mocked fixture was corrected and that module rerun successfully.
- Five new no-Git/no-subprocess/no-wait unit cases take **0.002 seconds total**.
  Existing module timings: review 7.95s, final 42.61s, evidence 6.70s, completion
  33.91s, execution 42.16s, end-to-end 34.39s, permissions 6.76s, exclusions 1.06s
  (parallel wall times). No new heavy workflow, full suite, live inference, or UI
  changes; no browser validation required. `git diff --check` passes.

Remaining limitations:

- The controller validates claim structure and candidate/check binding, not the
  semantic truth of a model's explanation. A precise invented static claim is
  not proven by filling these fields. Independent review still must assess it.
- A real failed check is a prerequisite for executable implementation repair,
  not proof that its failure demonstrates the claimed defect. Relevance of the
  regression and preservation of original/new assertion meaning remain explicit
  worker and independent-review obligations. Conventional test path recognition
  permits creating the probe; it is not a security sandbox or an assertion
  equivalence checker. Passing tests never automatically approve a claim or job.
- Historical records without these additive fields remain readable; historical
  evidence is unavailable rather than inferred. New decisions use the contract.


Update this card and TASKS.md; commit this repair separately from the exporter.
