# T46 — Explicit access policy and inexpensive route health

Status: Not started
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

## Completion record

Access classifications and scope contract: pending
Backward compatibility and acceptance evidence: pending
Health/probe provenance, failure categories, and avoided probes: pending
Commands/browser results and measured timing: pending
Remaining limitations: pending

Update this card and TASKS.md; commit independently of ranking changes.
