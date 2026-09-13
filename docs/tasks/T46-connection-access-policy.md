# T46 — Explicit access policy for available connections

Status: Done
Depends on: T45 findings recorded
Size: M

## Outcome

Distinguish public-free routes, operator-authorized included access, local models,
priced routes, and unknown pricing. Selection must establish which routes it may
use before ranking them.

## Existing behavior and read points

The latest trial pinned included pairs because unknown catalog prices do not
satisfy the automatic free-route filter. Do not solve this by globally labeling
unknown pricing as zero.

Inspect `cheapos/gateways.py`, `routing.py`, `model_pool.py`, connection/settings
serialization, plan authorization, and the existing Models UI. OmniRoute owns
credentials and provider routing; CheapOS owns the task's authorized access and
spending policy. Reuse these boundaries instead of duplicating provider plumbing.

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

## Acceptance

- Unknown catalog pricing alone never grants Free only eligibility. Included
  access is selected explicitly and never mislabeled as public free.
- Candidates outside the allowed scope are excluded before dispatch. No implicit
  paid/local fallback and no expansion of spending consent.
- Old configurations/tasks retain previous behavior. New optional fields do not
  rewrite an authorized run or invent historical billing information.
- Refresh preserves access choices and correct cooldown scope/reason.
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

## Completion record

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
