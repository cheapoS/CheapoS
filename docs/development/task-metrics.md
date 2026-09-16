# Task metrics and deterministic fixtures

New tasks carry metric schema 1. Each dispatched request stores role/model, purpose, response outcome, measured duration and only whitelisted reported token/cost fields. Input/output totals are separate from cached/reasoning subsets; subsets are never added a second time. Accounted cost/tokens always come from the existing reservation/reconciliation ledger, never from adding reservations and reported usage together.

Cost provenance distinguishes provider reports, configured estimates and retained uncertain reservations. None is a billing receipt. Unreported cached/reasoning usage stays unknown. Old tasks retain partial-historical coverage: absent fields are not inferred as zero. Request history is capped at 2,000 records and run timing at 500; truncation marks coverage partial.

Run elapsed time is measured while the controller is active. Provider-request time includes generation and network latency, cooldown time measures explicit waits, and operator time measures in-run test-approval waits. Controller work is the remainder. Time between stopped runs or awaiting a final human commit is not included. Incomplete run timing stays unknown. Cancellation is distinct from model failure. Reviewer approval and operator-accepted commits are separate outcomes; a later failed request does not inherit earlier human acceptance.

New HTTP request records additionally separate `pacing_seconds` (local provider
slot and quiet-interval waits) from `gateway_request_seconds` (network dispatch
through response consumption, including retries hidden inside a gateway). These
are components of the existing `seconds` total, not extra time to add to it.
Both survive HTTP failures; a cancelled queue has no gateway duration. Missing
historical values remain unknown. See [provider pacing](provider-pacing.md).

Export an explicitly selected local store:

```sh
python3 -B scripts/task_metrics.py --store /path/to/cheapos-data --output /tmp/task-metrics.json
```

The report includes anonymized task identifiers, known outcomes, calls, check/review counts, failures, repeated-read warnings, handoffs, recovery and approval/resume interruptions, usage provenance and measured timing. It omits prompts, source paths, model outputs, keys and environment values. There is no telemetry.

Run the seven pinned disposable fixtures:

```sh
python3 -B scripts/task_metrics.py --benchmark --output /tmp/benchmark.json
```

Fixtures cover a README edit, new utility, bounds bug, public-link answer with mocked public content, failed-check repair, reviewer revision and source commit conflict. Fixed source contents and requirements are fingerprinted. Actual check processes and source/patch assertions verify outcomes independently of provider prose. The README fixture simulates a human commit only inside its disposable repository. Fixture providers report synthetic usage; their results validate controller behavior, not real-model quality or savings. Running real models remains a separate explicit operator action with selected placement and budget.

Planner is a separate role in calls, role token/cost breakdowns, accounted totals,
routing traces and session details. Planning reservations and failures use the
same provenance as other roles. Existing worker attribution is historical and is
not redistributed. Missing role history stays unknown. Session identity prefers
the saved provider-reported model, falling back to the recorded requested route.
Planner compatibility observations do not imply a validated plan outcome;
`plans_completed` is not used for ranking without a durable outcome contract.
