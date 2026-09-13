# T48 — Qualify selection through the actual gateway path

Status: Not started
Depends on: T47
Size: M (a small live experiment, not a new broad benchmark suite)

## Outcome

Determine whether automatic choice across authorized available routes can finish
a known task. Earlier successful pinned pairs do not establish this behavior.
Prove the path used by the app, not merely a successful direct provider request.

## Design reference

FCM's [pinned router tests](https://github.com/vava-nessa/free-coding-models/blob/536af716263e514723594dd13e755fb06fcdec2d/docs/router-v2.md)
exercise request normalization and the real routing chain with fallback disabled.
Adapt that principle to CheapOS -> OmniRoute -> provider. Do not install FCM or
add a new backend as part of this trial.

## Work

1. Reuse one small disposable qualification fixture with independent tests. Freeze
   app SHA, fixture/test hashes, configuration, and behavior. Record the planned
   attempt count and known resource expectations before running. Start with one
   automatically selected run, not the whole difficulty matrix.
2. Establish the explicitly allowed access scope and current route availability.
   Use Free only unless included access is already expressly authorized for this
   trial. Unknown prices and historical quota screenshots are not new authority.
   Do not modify global preferences or exhaust connections to collect more samples.
3. Use measurement mode with retained accounting, spending policy, command scopes,
   Pause, and error recovery. Record selected models, selection reasons, probes,
   handoffs, and route-availability failures.
4. Observe rather than coach after Start. If intervention is needed, record it and
   label the attempt assisted. Retain failures; avoid repeated Resume without a
   changed condition.
5. Inspect required check results, immutable acceptance files, reviewer evidence,
   completed commit receipts, and unchanged source main. App readiness and a
   feature commit are necessary but independent requirements must also pass.
   Do not merge or push the fixture project.
6. If another comparison is warranted, propose a small matched comparison with
   unchanged app/fixture versions. Do not infer production success rates or causal
   improvements from mixed models, revised tests, and retries.

### Minimal path qualification before the automatic run

- Inspect existing readiness evidence first. Reuse fresh compatible observations
  where they establish the required contract. If a new check is needed, target
  only the intended worker/reviewer routes and record its request cost/count.
  This preflight is separate from the automatic execution outcome.
- Use the app's real gateway adapter, serialization, stream parser, and tool-call
  validation. A direct curl to a provider or a one-token greeting does not prove
  this path. A minimal non-mutating structured tool response is sufficient here;
  do not add a second coding benchmark before the actual task.
- Pin each route and disable fallback for that targeted diagnostic where the
  gateway supports it. Record the requested and served identity/provenance.
  If fallback cannot be disabled or the identity cannot be established, disclose
  the limitation and do not label the diagnostic a qualified pinned-model test.
- The subsequent real task must use the automatic selection policy being tested,
  not accidentally inherit those diagnostic pins. Keep both phases' accounting
  separate and include all probes in the combined experiment cost.
- Inspect T47 traces for skip reasons, dispatch order, gateway fallback visibility,
  and reviewer identity. User-visible explanations must agree with recorded events.
  Demonstrate only naturally occurring live failures; use cheap offline fixtures
  for forced quota/auth/malformed-response cases instead of exhausting an account.
- Use the same prompt, tools, and gateway path relevant to the task. If a direct
  provider call succeeds but the app path fails, record a compatibility failure;
  do not quietly switch to the direct provider and claim the integration passed.

## Acceptance

- A dated report identifies whether automatic selection was exercised and whether
  the task completed independently, failed, or needed assistance.
- Retain selected routes/access basis, exact identities, provider/check time,
  request/token totals and cost uncertainty, interventions, and verified receipts.
  No credentials or personal data in committed evidence.
- Distinguish quota failure from capability/quality failure. Do not probe known
  exhausted sibling pools or fall back outside authorization.
- Keep unsuccessful attempts. A success supports only the observed task/configuration,
  not a promise that every free model works.
- Identify the next concrete bottleneck from evidence. Do not set restrictive
  default budgets from one sample or merely recommend raising limits again.
- Distinguish endpoint reachability, structured tool support, observed model
  identity, and independently verified task completion. Passing one stage does
  not imply the later stages passed.
- The report separates targeted pinned diagnostics from automatic task execution,
  retains all probe usage, and reports any hidden gateway attempt chain as unknown.

## Validation and test-cost boundary

This is an explicitly selected live product experiment, not a new everyday test.
Keep it outside automatic regression discovery and reuse existing focused
acceptance. No new heavy regression, full-suite gate, or live inference in normal
developer checks. Disclose costly proposed follow-up tests before adding them,
under AGENTS.md; do not silently grow another expensive matrix.
Preflight must not become an all-model sweep, recurring background benchmark, or
per-chat full test. Tests for diagnostic routing should use fake transports/clocks
and complete quickly; real model latency belongs only to this selected trial.

## Completion record

Fixture/app/configuration identity: pending
Task IDs, selected routes, and actual outcome: pending
Gateway-path diagnostics, pins/fallback behavior, and served identities: pending
Independent checks and receipts: pending
Timing/usage/interventions: pending
Remaining limitations and next recommendation: pending

Update this card and TASKS.md; commit only the sanitized experiment record.
