# T47 — Prefer models with evidence of completing work

Status: Done
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

Outcome fields and ranking rules: role_evidence adds completion_samples,
completed (not independently disproved), independently_validated,
independently_disproved and human_integrated. Existing compatibility samples stay
separate. Rank preserves a configured preference, then observed independent
validation/completion, disproof, and compatibility/tie-break evidence. A single
completion may beat fast invalid work; it is an observation, never an accuracy
estimate. Eligibility, cooldowns, distinct reviewer and durable exclusions remain
upstream of ranking. No model names or assumed parameter counts establish quality.

Attribution: new request metrics capture branch_item_id beside T46 dispatch_scope.
Completed operation must match run/item/candidate, exact 40/64-character SHA and
feature-parent continuity; immutable receipt is reconstructed against its original
required checks and criteria. Only one unambiguous dispatched connection/model
scope per role earns a sample. Missing historical or truncated provenance is
unknown, not inferred from current providers. A receipt is counted once across
Resume/restart/re-read; accepted flags and original observation times survive
activity rereads. Observation occurs after durable commit publication and during
Resume/final preview for backfill. No current-workspace test/Git rerun is needed.

Connection isolation: pool keys include optional opaque connection revision for
health, cooldown, probe, outcome and completion records. Legacy None accesses
legacy unscoped records only. Engine/routing pass actual dispatch binding and
Models uses the current gateway revision. Credentials are neither persisted nor
hashed into a public quality identity.

Trusted independent hook: local Python
`pool.adjudicate_completion(endpoint, model, role, receipt_id, evidence_digest,
passed, connection_revision)` accepts only an existing exact receipt and a retained
independent artifact SHA256 with boolean verdict. It is not exposed through worker
tools or HTTP. Observer caller must validate the actual candidate before invoking
it; a hash alone is not proof. Repeated artifacts are idempotent, conflicting
verdicts for the same artifact fail, disproof stays sticky for that receipt.
A new candidate requires a new receipt. A completed controller merge separately
marks human_integrated; review syntax alone never becomes independent validation.

Validation: selector exposed 60 dependent modules because engine imports are
broad; used focused pool/routing/access/gateway and existing commit/merge coverage
instead of a full suite. New synthetic receipt tests use no Engine, Git, sockets,
real waits or model calls. Five new tests measured 0.018 seconds including module
setup; covers malformed receipts/checks/SHA lengths, handoff-safe scoped identities,
restart deduplication, invalidation, retained acceptance, rank/pins, and scoped
cooldown/probe isolation. Existing routing25 passed9.266s; model_pool21 passed9.528s;
gateways18 passed0.141s; commit-controller2 passed9.992s; outcomes2 passed within
0.050s with four earlier new cases. Completion fixture now supplies the real small
pool dependency; final rerun:6 existing completion tests passed33.086s (11 tests including the five
new tiny cases passed33.168s). Initial gateway
socket restriction was rerun with loopback permission; initial completion fixture
lacked gateway, not a product failure. No assertions were removed.

UI by coordinating agent commit528191c: 58 focused Node tests pass88ms; three new
cases total about0.77ms. Shows observed completions/no prior completion evidence,
separate independent/human counts, and compatibility without accuracy claims.
Browser verification is not newly claimed here.

Remaining limitations: independent observations require a trusted local observer;
there is no automated external verifier or inferred billing/accuracy. History is
bounded (128 completion receipts per route/connection, 30-day visible window).
No historical model-quality backfill without captured scope. Core task status,
files, usage and recovery limits remain unchanged. No live qualification ran in
this card; T48 owns it. TASKS.md is updated by the coordinating agent.
