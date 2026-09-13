# T46 — Explicit access policy and inexpensive route health

Status: Done — expanded code and focused checks; browser verification pending
Depends on: T45 findings recorded
Size: M

## Outcome

Distinguish public-free routes, operator-authorized included access, local models,
priced routes, and unknown pricing. Selection must establish which routes it may
use before ranking them.
Keep availability evidence fresh without spending the free allowance on repeated
health checks, and distinguish the cause of failure before choosing a response.

## Existing behavior and read points

The latest trial pinned included pairs because unknown catalog prices do not
satisfy the automatic free-route filter. Do not solve this by globally labeling
unknown pricing as zero.

Inspect `cheapos/gateways.py`, `routing.py`, `model_pool.py`, connection/settings
serialization, plan authorization, and the existing Models UI. OmniRoute owns
credentials and provider routing; CheapOS owns the task's authorized access and
spending policy. Reuse these boundaries instead of duplicating provider plumbing.

## Design references

The free-coding-models review used commit
`536af716263e514723594dd13e755fb06fcdec2d`. Useful references are its
[versioned probe cache](https://github.com/vava-nessa/free-coding-models/blob/536af716263e514723594dd13e755fb06fcdec2d/src/core/probe-cache.js),
[failure classifier](https://github.com/vava-nessa/free-coding-models/blob/536af716263e514723594dd13e755fb06fcdec2d/src/core/router-v2/failure-classifier.js),
and [catalog drift detection](https://github.com/vava-nessa/free-coding-models/blob/536af716263e514723594dd13e755fb06fcdec2d/src/core/models-drift.js).
Adapt the ideas to current CheapOS code. This card does not add the FCM daemon,
install its package, import its provider credentials, or introduce another router.

## Work

1. Add the smallest explicit access classification in existing connection settings.
   Keep pricing provenance separate from an operator's statement that specified
   connection/model access is included in their account.
2. Scope included access to the intended connection and allowed models or defined
   pool. Bind the choice to the inspected run configuration. A changed endpoint,
   alias, or newly discovered model must not inherit unrelated authorization.
3. Present a simple Models choice with honest labels: public free, included
   access, local, priced, or unknown. Explain included estimates without requiring
   raw price editing. Preserve existing configured free/local behavior.
4. Keep capability and availability separate from access. Catalog membership does
   not prove tool-capable inference. Reuse probes/cooldowns; show known retry times
   and unknown resets honestly. Settings inspection must not spend paid inference.
5. Keep quota scopes distinct: one exhausted model pool does not exclude every
   model behind the gateway. Retain provider-wide cooldown where a shared quota
   is actually established.
6. Preserve current key handling. No credentials, raw account errors, personal
   identifiers, or task content in health records, reports, or committed fixtures.

### Health and discovery details

Implement these as small extensions of the existing gateway/pool, after the access
classification works. Do not create a second availability cache or a global scan.

- Store the source and observation time of metadata/health facts. Treat catalogs
  as discovery inputs: keep current provider-confirmed pricing authoritative for
  free eligibility, and label community claims or unknown values accordingly.
  Reuse available gateway/provider metadata to flag changed context/output limits
  or capabilities. Report discrepancies without overwriting curated settings,
  expanding access, or modifying an authorized run. Do not add a new mandatory
  external catalog dependency solely to implement drift detection.
- Extend cached tool checks with a probe-contract version and relevant nonsecret
  configuration identity. Invalidate when the endpoint, model, credential
  configuration revision, or probe requirements change. Do not store the key or
  a reusable derivative of it in health data. A cached success establishes only
  the capability it tested, not current quota or permission to spend.
- Prefer recent actual request results and reliable quota/reset headers exposed
  by OmniRoute. Preserve provider/model/account scope and units. Unknown remaining
  quota is unavailable, never zero or 100%. Do not bypass OmniRoute to scrape
  accounts or fetch credentials when metadata is absent.
- Probe only the needed eligible candidates with bounded concurrency and existing
  probe accounting. Reuse fresh observations, share an in-flight probe when safe,
  and back off failures. No scan of every catalog entry at startup or each chat
  turn. Keep current freshness defaults unless a measured reason warrants change;
  do not copy FCM's durations as new arbitrary CheapOS limits.
- Normalize failures into useful categories: credential/access, malformed request,
  model capability mismatch, unavailable route, rate limit/quota, transient
  provider/transport error, and invalid/incomplete response. Map each to retry,
  cooldown scope, quality impact, and operator action. Caller mistakes and user
  cancellation must not damage every candidate's model-quality record.
- Classify using structured context as well as HTTP status. A 404 may indicate a
  removed model or wrong endpoint; do not universally call it a client mistake.
  Failed credentials apply to the affected connection, not unrelated credentials
  for that provider. A 429 does not prove all gateway pools share a quota.
- Preserve existing content/tool validation: HTTP 200 is not sufficient, reasoning
  activity alone is not a completed answer, and partial tool arguments never
  execute. Reuse streaming/provider checks rather than a second parser.

## Acceptance

- Unknown catalog pricing alone never grants Free only eligibility. Included
  access is selected explicitly and never mislabeled as public free.
- Candidates outside the allowed scope are excluded before dispatch. No implicit
  paid/local fallback and no expansion of spending consent.
- Old configurations/tasks retain previous behavior. New optional fields do not
  rewrite an authorized run or invent historical billing information.
- Refresh preserves access choices and correct cooldown scope/reason.
- Repeated selection with a fresh matching tool check dispatches no extra probe;
  a changed probe/configuration identity invalidates that cached check. A quota
  cooldown cannot be bypassed by an older successful observation.
- A malformed caller request does not mark several healthy models broken;
  credential failure excludes only its connection; a genuinely model-specific
  incompatibility remains recorded as such. User Pause is not a model failure.
- Stale/conflicting metadata is visibly qualified. External catalog membership
  cannot confer free eligibility or silently change an accepted plan.
- Focused cases cover classifications, absent/contradictory pricing, stale
  authorization, excluded candidates, and scoped quotas. UI checks cover refresh
  persistence without returning secret fields.

## Validation

Use synthetic catalogs/provider fixtures. Run affected fast cases in gateway,
routing, model-pool, configuration, and authorization modules, plus focused
Node/UI checks. Prefer pure selection tests and reuse existing execution
coverage. No full suite, personal-account experiment, or new heavy integration
case by default. Disclose any proposed heavy case before adding it; T48 handles
real automatic selection separately.
Use injected clocks and scripted response headers for freshness/backoff cases;
never sleep through a real cooldown or launch repeated live probes in a test.
Extend existing parser/classifier tests with table-driven inputs. Record the
runtime of new cases and disclose any proposed heavy test before introduction.

## Previous completion record (before expanded requirements)

Access classifications and scope contract:

- `gateway.json` now persists an opaque `connection_revision` and exact
  `included_models`. Saving grants requires `expected_connection_revision` from
  the inspected connection. Endpoint/client-key changes rotate the revision and
  clear grants; refresh/startup-preference changes retain them. Keys remain in
  memory/environment, never in this file or health records.
- Catalog `access_class` is separate from unchanged advertised prices and `free`:
  `public_free`, `included`, `local`, `priced`, or `unknown`. Included provider
  configs carry an explicit binding, `pricing_source: operator_included`, original
  `catalog_pricing`, and zero marginal-cost estimates. Positive provider-reported
  charges still count; included access is not a public-free price claim.
- New task/route snapshots and branch proposal model policy capture the exact
  connection scope. Selection excludes unauthorized candidates before ranking;
  dispatch (including override/probe requests) rechecks current scope, exact
  model, endpoint, and tool eligibility. No paid/local fallback was added.
  Included cached tool probes require the same connection revision.
- Request metrics retain the dispatched endpoint/revision/model/role separately
  from later handoffs. Health errors use model scope unless machine metadata
  explicitly establishes provider-wide cooldown. Missing reset times remain
  unknown; raw upstream error text is never retained by this parser.

Backward compatibility and acceptance evidence:

- Existing tasks/contracts without access fields retain their legacy policy;
  historical prices are not rewritten. Catalog refresh alone cannot authorize
  new model IDs or change a saved included scope. Auto/combo/local entries are
  excluded from included remote authorization.
- Pure cases cover absent and contradictory prices, exact IDs, stale revisions,
  unknown models, local/combo exclusion, scoped cached probes, old-task behavior,
  proposal invalidation, and sanitized quota metadata. Existing gateway, routing,
  handoff, cooldown and branch authorization tests pass.
- Models has an explicit exact-ID grant list, per-role included choice, honest
  catalog labels, refresh persistence, and no inference when saving settings.
  UI work is separately committed by the UI owner on this branch.

Commands/browser results and measured timing:

- Inspected `scripts/check.py --plan`: shared engine/provider imports select 60
  modules, so used focused cases instead of that broad set.
- 117 distinct backend tests pass across `test_access_policy` (7),
  `test_gateways` (18), `test_routing` (25), `test_model_pool` (21), `test_http`
  (33), `test_branch_start` (3), `test_branch_reprepare` (2), and
  `test_cooldown_wait` (8). Loopback tests were rerun with loopback access after
  sandbox socket denial; this was not an application failure.
- Seven new deterministic cases total **0.013 seconds**, with no Git, inference,
  real-time waits, or new server fixture. Existing combined focused runs took
  about 9–11 seconds in parallel. No full suite or account experiment.
- UI owner reports 55 Node tests passing in about 80ms; synthetic Models browser
  validation is recorded by the parent at integration. `git diff --check` passes.

Remaining limitations:

- An operator's included-access statement is not a billing guarantee. Unknown
  prices remain unknown, and reported costs override estimates.
- Exact manual IDs can be authorized before appearing in a catalog; that does not
  prove availability or tool support. Automatic selection still requires current
  catalog membership and advertised tools followed by a real valid tool probe.
- CheapOS observes its own endpoint/key configuration changes. An invisible
  upstream alias reassignment or environment credential replacement at restart
  behind identical endpoint/model IDs cannot be detected from catalog metadata;
  the operator must reconfirm access after such a change. No secret-derived
  fingerprint or claimed upstream account identity is stored.
- Broader quality/ranking history scoping is T47; this task only adds immutable
  dispatch provenance and connection-bound included-probe reuse.


Update this card and TASKS.md; commit independently of ranking changes.

Browser qualification remains pending: Chrome rejected both loopback addresses with `net::ERR_BLOCKED_BY_CLIENT`; in-app browser was unavailable. No UI action succeeded. The disposable synthetic server was stopped. Focused Node and backend coverage passed; this is not a visual pass.

## Expanded requirements completion

Implemented required-marker probe version 2 and connection/model/metadata-bound
cache identity. Matching successes retain the existing 300-second freshness;
concurrent callers share an in-flight probe instead of issuing duplicate calls.
Cooldowns always override a success. Catalog observation source/time, staleness
and changed context/output/capability fields appear in Models without changing
access grants or accepted plans. No second registry or external catalog dependency.

Structured failure categories separate caller, credential/access, capability,
route availability, quota, transport, cancellation and response failures. Caller
mistakes/cancellation do not become model-quality failures. Connection and
provider/model cooldowns remain scoped, with unknown reset times honest. No raw
errors or credentials are added to health evidence. Remaining quota is unavailable
when the gateway does not supply it; no account scraping or inferred balances.

Validation: six new pure health cases pass in 0.003 seconds. Existing focused
routing25, model-pool21, access7, gateway18, cooldown8, output-recovery7,
compact-edits20, planning-HTTP8 and branch-worker-recovery4 pass. Fixtures now
return the explicit marker; assertions remain intact. No full suite or live
regression was added. UI coverage is recorded under T47.

Browser verification remains pending after the earlier loopback client block.
Invisible upstream credential/alias changes cannot be detected from local
configuration; reconfirm access when that configuration changes externally.
