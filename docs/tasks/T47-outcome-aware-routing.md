# T47 — Outcome-aware routing with visible decision traces

Status: Done — expanded code and focused checks; browser verification pending
Depends on: T46
Size: M

## Outcome

Among eligible routes, prefer evidence of useful work for the requested role.
A successful probe or valid APPROVE envelope does not prove the user's
requirements were completed correctly.
Make the full selection/attempt path inspectable inside the CheapOS conversation,
including the difference between the requested route and the model actually used.

## Existing behavior

`FreeModelPool` already records role-specific calls, edits, checks, checkpoints,
reviews, invalid output, and acceptance in bounded local history. Routing uses
those observations and durable worker exclusion; branch execution now records
outcomes. Extend these mechanisms rather than rebuilding a registry.

Read `cheapos/model_pool.py`, `routing.py`, `branch_worker_recovery.py`,
`branch_controller.py`, `branch_evidence.py`, and commit/final-readiness receipts.
The matrix is qualification evidence, not a static list of universally best models.

## Design references

Use FCM's [per-request decision trace](https://github.com/vava-nessa/free-coding-models/blob/536af716263e514723594dd13e755fb06fcdec2d/src/core/router-v2/decision-trace.js)
and [task-specific recommendation logic](https://github.com/vava-nessa/free-coding-models/blob/536af716263e514723594dd13e755fb06fcdec2d/src/core/utils.js)
as design references. Its [stability score](https://github.com/vava-nessa/free-coding-models/blob/536af716263e514723594dd13e755fb06fcdec2d/docs/stability.md)
describes request reliability/latency, not verified coding correctness. Keep
those signals distinct in CheapOS; do not import its numerical weights or
self-reported benchmark tiers as proven worker/reviewer quality.

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

### Decision traces and model fit

- Extend existing request metrics/events with one bounded trace per logical
  request: role, requested route, ordered candidates skipped with stable reason
  codes, actual dispatch attempts, elapsed time, failure category, and selected
  or reported served identity. Separate a cached observation from a dispatched
  probe and from an actual work request. Reuse request/run IDs for correlation.
- Capture the actual served model when the gateway exposes trustworthy metadata.
  Record its provenance; if identity is not observable, say unknown instead of
  repeating the requested alias as fact. Never assume two aliases guarantee
  different underlying worker/reviewer models. Preserve existing independent
  review requirements; an opaque route cannot manufacture independence evidence.
- Keep CheapOS handoffs distinguishable from gateway-internal fallback attempts.
  If OmniRoute does not expose its internal chain, label that portion unavailable.
  Do not invent attempts, count them twice, or create a second automatic routing
  daemon to collect them. Spending/uncertain-request accounting remains intact.
- Present a concise orchestration message, for example "Skipped A: quota exhausted;
  using B." Put the ordered details inside the existing reply's Details disclosure.
  Include useful next actions when no route remains; avoid adding another floating
  status panel. Preserve open Details, the draft, and scroll behavior on updates.
- Store only bounded routing metadata, safe model/connection labels, and sanitized
  reason codes. Exclude keys, raw headers/error bodies, prompts, outputs, and private
  endpoint/account identifiers. Old tasks without traces remain readable.
- Apply capability/context fit before ranking: a known insufficient context or
  missing required tool capability cannot be overcome by a fast latency score.
  Worker versus reviewer role is already known; infer other needs from the task
  rather than making the operator answer a questionnaire on every message.
  Unknown fit remains qualified, not silently treated as adequate.
- Use measured latency/reliability as supporting operational evidence. Available
  response samples can reveal slow tails, but do not add probes just to populate
  a dashboard or report a precise quality percentage from a handful of calls.

## Acceptance

- Repeated invalid/incomplete work cannot gain preference solely through a fast
  response when a comparable eligible candidate has substantiated completions.
- Role attribution survives handoffs/restart; repeated observation is idempotent.
- Availability outages and independently disproved results remain distinct from
  implementation failures and qualified outcomes.
- Legacy missing fields and tiny samples do not produce strong quality claims.
- Selection obeys access policy/cooldowns and visibly explains a handoff or lack
  of eligible routes. No hidden model upgrade.
- A fixture with skipped, failed, and successful candidates yields one correctly
  ordered trace and truthful chat summary. Reload does not duplicate attempts;
  unsupported gateway trace fields remain explicitly unavailable.
- Requested and served identities are distinct when they differ. Unknown or
  aliased identity cannot be reported as proof of independent review.
- Traces contain no credential/prompt/raw error data. An excluded model that was
  never contacted contributes no fabricated request usage or response sample.
- Fast but known-incompatible candidates are excluded before quality ranking;
  supporting latency evidence cannot outweigh required access/capability checks.

## Validation

Use small deterministic ranking/receipt fixtures in existing pool/routing tests.
Reuse synthetic receipts; do not create a multi-minute branch run to test a
sorting rule. Include targeted existing handoff cases only where behavior changes.
Report new-case timings and selected test count/time. No live inference, full
suite, or new heavy regression is part of this card.
Test trace ordering/redaction/identity with tiny synthetic gateway responses and
fake time. Use pure Node presentation tests plus one relevant disposable UI check
for Details placement. Do not build a long live failover scenario as a regression.

## Previous completion record (before expanded requirements)

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

## Expanded requirements completion

Retained completion-based ranking and added bounded routing traces, correlated
with task turns and request IDs. Ordered exclusions/probes/cached observations,
actual dispatch status/time/failure categories and selection are shown inside
the reply's existing Details. No fabricated usage for uncontacted candidates.
Trace metadata is allowlisted; prompts, raw errors, endpoints and keys are absent.

Requested model and gateway-reported served model are distinct. Missing or
conflicting response metadata is unknown; internal gateway attempts are unavailable.
New-task review guards reject opaque unresolved aliases and detected identical
worker/reviewer identities before executing review tools. Exact named routes with
missing metadata retain configured separation, explicitly not proven underlying
identity. Legacy task policy remains readable. A provider-reported model field is
not independent attestation of internal gateway routing.

Known explicit context requirements and advertised tool capability are checked
before ranking. Unmeasured current context remains qualified as unknown; historical
request token counts are not reused as a false current requirement after compaction.
No tokenizer estimate is presented as exact fit or quality evidence.

Validation: three new pure trace tests take under 0.001 seconds; four new identity
cases take 0.010 seconds. Existing streaming12 and engine20 pass in 0.646 and
4.637 seconds. 74 focused Node checks pass in about 84ms, including actual Details
markup. Draft/scroll/disclosure handlers remain unchanged. Additional identity
fixture verification is recorded with its follow-up commit. No new heavy test.
Browser verification remains pending due to the previously recorded client block.
