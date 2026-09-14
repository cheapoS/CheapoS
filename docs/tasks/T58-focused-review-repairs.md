# T58 — Turn review findings into focused repairs and evidence-based decisions

Status: Done
Priority: High — convergence
Depends on: T49, T51, T57
Size: M
Planning baseline: `5a463b4`, September 14, 2026

## Outcome

A two-line defect normally leads to a localized correction and relevant
verification. A passing implementation is not repeatedly rewritten to satisfy
an unsupported preference. Real correctness, scope, security and explicit project
requirements can still block approval even when existing tests pass.

## Entry points and existing behavior

Read [branch_disagreement.py](../../cheapos/branch_disagreement.py),
[branch_review.py](../../cheapos/branch_review.py),
[branch_final.py](../../cheapos/branch_final.py),
[engine.py](../../cheapos/engine.py) (repair packets, compact context, write tools),
and [work_policy.py](../../cheapos/work_policy.py).

The current repair instruction already says to verify a reviewer's claim and
preserve tests. Extend that contract; another generic instruction to “be careful”
is not the implementation. T51 owns edit-version mechanics; T60 owns durable
dispute identity and repeated-cycle handling.

## Work

1. Build a compact repair brief from canonical findings: original requirement
   reference, affected file/symbol/range, expected versus observed behavior,
   supporting evidence, and relevant existing checks. Keep it attached to the
   active item across compaction and handoff without repeatedly copying the full
   review history into every prompt.
2. Instruct the worker to preserve unaffected functions and apply the smallest
   coherent change. Require an explanation when a broader edit is necessary;
   do not impose a fixed line-count rule that makes a legitimate refactor
   impossible. Continue using version-bound tools and their current limits.
3. Require a disposition for each finding: reproduced and corrected, disproved
   with counterevidence, or still unresolved. Reference the candidate and concrete
   check/source evidence. A worker's label alone cannot establish correctness or
   authorize a command; independent review assesses the evidence.
4. Give the next reviewer the original claims, the focused diff since that
   candidate, and the worker's evidence/dispositions. Avoid asking it to start an
   unrelated style review from scratch each time. Preserve access to the full
   candidate where needed to check regressions.
5. Make blocking criteria explicit: a supported requirement violation, defect,
   regression, or consequential issue. Optional naming, formatting, or architectural
   preferences are non-blocking unless grounded in accepted requirements or
   applicable project guidance. Do not discard legitimate scope enforcement as
   a nit merely because the resulting code passes tests.
   Keep optional suggestions separate from the blocking `defects` array so they
   do not contradict T56's explicit approval contract.
6. Treat matching passing checks as strong evidence, not automatic approval or
   complete test coverage. To reject behavior those checks exercise, explain
   the uncovered case or why the evidence does not establish the requirement.
   Style suggestions may accompany approval but never imply a repair obligation.
7. Reuse verification only while candidate/command/environment identities still
   match. A real edit needs applicable verification; an unchanged candidate does
   not need the same test rerun merely because another review turn occurred.

## Acceptance

- A synthetic localized defect produces a brief tied to its exact requirement
  and location, with unaffected behavior preserved in the requested repair scope.
- A verified counterexample reaches the next reviewer intact; repeating an
  already disproved assertion is not treated as new evidence.
- Optional style advice cannot alone trigger REQUEST_CHANGES. A concrete defect
  missed by passing checks can still block approval.
- Explicit project conventions and item scope remain enforceable.
- Repair briefs survive compaction/handoff and do not omit unresolved findings.
  No new checks execute merely because the reviewer suggested a command.

## Focused validation and handoff

Start with the selector plan. Prefer pure brief construction and scripted review
exchanges; reuse existing disagreement/check-reuse cases. Do not add a full
multi-item live or Git workflow to demonstrate prompt construction. Report which
behavior is controller-enforced versus model guidance, actual new-case timing,
and any untested live convergence hypothesis. Preserve the no-heavy-test rule,
commit the change, and update this card and TASKS.md.


## Completion record — September 14, 2026

Implementation: `e0fcc51` (with foundations `abe2545`, `226b604`, `3b48cef`).

Canonical findings now produce compact persistent repair briefs with original references, candidate, location, expected/observed behavior and check evidence. A checkpoint requires a concrete per-finding disposition; the controller binds it to the new candidate and retains counterevidence for independent judgment. The next item reviewer sees the prior claims and patch difference since the claim. Changed files outside finding locations require a broader-edit explanation; preserving unaffected functions within a file is model guidance, not a semantic proof. Optional advice is separate from blocking defects; advice alone cannot authorize repair. Current verification reuse retains the existing candidate/command/environment identity guards.

Validation: pure localized-patch, evidence, optional-advice and persistence cases pass; existing branch review/execution selection passed eight cases in 130.610s, including scripted repair/commit and verification reuse. No live convergence claim; broader repair justification and truth of counterevidence still require independent review.
