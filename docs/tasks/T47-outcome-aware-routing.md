# T47 — Prefer models with evidence of completing work

Status: Not started
Depends on: T46
Size: M

## Outcome

Among eligible routes, prefer evidence of useful work for the requested role.
A successful probe or valid APPROVE envelope does not prove the user's
requirements were completed correctly.

## Existing behavior

`FreeModelPool` already records role-specific calls, edits, checks, checkpoints,
reviews, invalid output, and acceptance in bounded local history. Routing uses
those observations and durable worker exclusion; branch execution now records
outcomes. Extend these mechanisms rather than rebuilding a registry.

Read `cheapos/model_pool.py`, `routing.py`, `branch_worker_recovery.py`,
`branch_controller.py`, `branch_evidence.py`, and commit/final-readiness receipts.
The matrix is qualification evidence, not a static list of universally best models.

## Work

1. Audit which branch events reach the pool and their attribution across handoffs.
   Use completed matching receipts and current required checks to distinguish
   useful candidate completion from tool activity. Human acceptance/integration
   remains different from feature-branch completion.
2. Keep worker and reviewer observations separate. Completing review response
   syntax is compatibility evidence, not judgment quality. If a later trusted
   independent check disproves a result, retain that outcome instead of counting
   it as independently successful. Do not accept an arbitrary worker claim as
   independent validation.
3. Define minimal additive fields and deterministic ordering. Eligibility and
   cooldowns come first; preserve explicit pin semantics. Do not infer capability
   from a name, tier, or one fast reply. Sparse evidence remains unknown.
4. Scope observations to the correct endpoint/connection/model and role. Resume,
   restart, and rereading receipts must not multiply samples. Preserve partial
   work/failure distinctions. Quota outages are not code-quality failures.
5. Explain choices briefly in existing activity/Models UI: observed completion,
   or no prior completion evidence. Show sample counts without fabricated
   accuracy scores or claiming mixed fixtures are controlled comparisons.
6. Integrate T46 eligibility and existing handoffs. Preserve candidate context,
   files, usage, distinct reviewer requirements, and durable recovery exclusions.
   Never renew exhausted recovery allowances to favor a ranked model.

## Acceptance

- Repeated invalid/incomplete work cannot gain preference solely through a fast
  response when a comparable eligible candidate has substantiated completions.
- Role attribution survives handoffs/restart; repeated observation is idempotent.
- Availability outages and independently disproved results remain distinct from
  implementation failures and qualified outcomes.
- Legacy missing fields and tiny samples do not produce strong quality claims.
- Selection obeys access policy/cooldowns and visibly explains a handoff or lack
  of eligible routes. No hidden model upgrade.

## Validation

Use small deterministic ranking/receipt fixtures in existing pool/routing tests.
Reuse synthetic receipts; do not create a multi-minute branch run to test a
sorting rule. Include targeted existing handoff cases only where behavior changes.
Report new-case timings and selected test count/time. No live inference, full
suite, or new heavy regression is part of this card.

## Completion record

Outcome fields and ranking rules: pending
Attribution/compatibility evidence: pending
Commands and measured timing: pending
Remaining limitations: pending

Update this card and TASKS.md; commit before controlled live qualification.
