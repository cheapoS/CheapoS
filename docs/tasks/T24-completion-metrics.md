# T24 — Task-level metrics and trustworthy cost display

**Depends on:** none. **Size:** M. **Result:** cheapoS can judge efficiency by completed work, not inflated token-saving claims.

## Read first

Usage reservation/reconciliation, task events, check/review/commit outcomes, model-pool observations, `renderTask`'s compute-savings pill, and the check-in's scorecard.

## Implementation

1. Define a versioned local task/run metric record derived from durable evidence: task outcome, user-approved commit where present, check/review outcomes, worker/reviewer calls, tool failures, repeated reads, handoffs, recovery attempts, elapsed time, and operator approval/resume interruptions.
2. Separate time working, waiting for provider, and waiting for the operator where the events support it. Mark unavailable historical fields unknown. Do not fabricate exact metrics from partial old records.
3. Record input/output/reasoning/cached tokens when reported, total accounted usage, and whether monetary cost is provider-reported or estimated. Retain uncertain reservations without double-counting after reconciliation. $0.00 in configured accounting is not a billing receipt.
4. Remove the current fixed hypothetical frontier-rate savings claim from the main UI. Show actual accounted usage/cost and provenance. A comparison is allowed only when its baseline and methodology exist and are labeled.
5. Add a deterministic benchmark fixture set based on the check-in: README edit, utility, bug fix, public-link question, failed-check repair, reviewer revision, and commit conflict. Pin source baselines/requirements and verify outcomes independently of the model's prose.
6. Provide a local report/export command with summary metrics and anonymized fixture identifiers. Do not include private prompts, raw logs, source paths, keys, or automatic telemetry. Real-model trial runs are a separate explicit operator action with known placement/budget.

## Acceptance

Fixture outcomes/counters match known events. Cancellation is not scored as model failure, reviewer approval is not labeled human acceptance, and no-usage fields stay unknown. Reconciled costs count once. The UI no longer displays invented dollar savings. Reports include success and interventions as well as tokens/time.

## Validation / limits

Add aggregation tests with old/new/interrupted records and a deterministic benchmark smoke run. No paid inference, external analytics account, leaderboard service, or claim that the single earlier live sample proves general savings. T25/T26 consume this data.

## Completion record

Status: Done

- Behavior delivered: Versioned local request/run instrumentation and evidence aggregation, reported token subsets and cost provenance, measured run/provider/cooldown/approval/controller timing, cancellation/acceptance distinctions, anonymized local export CLI, and seven pinned deterministic controller benchmarks. Removed the fixed hypothetical frontier-rate savings claim.
- Acceptance evidence: Aggregation covers reconciled cost counted once, token subsets, unknown historical fields, uncertain reservations, cancellation, and later failures after prior commits. Benchmarks independently verify README/utility/bug/public-link/repair/revision/conflict outcomes with actual checks and disposable sources.
- Commands and results: 17 sample/tool-argument/cooldown/HTTP integration tests passed in 22.400s. Metrics plus seven-scenario benchmark smoke: 5 tests passed in 25.905s. CLI benchmark reported all seven passed. JavaScript syntax and 69 guidance/conversation tests passed. Local store export/privacy check passed.
- Browser scenarios and results: CUA isolated port 51031: completed sample displayed 75 accounted tokens, $0.00, Provider-reported cost; hypothetical Saved dollars text absent. Sample still distinguished reviewer approval from human commit acceptance.
- Remaining limitations: docs/development/task-metrics.md defines timing coverage, unknown fields, provenance and history bounds. Fixture usage is synthetic and no live-model quality/savings claim is made. Time outside active runs is unmeasured. Accounted cost is not a provider billing receipt; export is local and opt-in.

Before implementing, read [TASKS.md](../archive/TASKS.md) for the shared contract. Update this record and the matching board row when complete.
