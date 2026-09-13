# T46 — Explicit access policy for available connections

Status: Not started
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

Access classifications and scope contract: pending
Backward compatibility and acceptance evidence: pending
Commands/browser results and measured timing: pending
Remaining limitations: pending

Update this card and TASKS.md; commit independently of ranking changes.
