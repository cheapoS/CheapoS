# T48 — Qualify automatic selection on a fixed small task

Status: Done — controlled attempt recorded; selection failed
Depends on: T47
Size: M (a small live experiment, not a new broad benchmark suite)

## Outcome

Determine whether automatic choice across authorized available routes can finish
a known task. Earlier successful pinned pairs do not establish this behavior.

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

## Validation and test-cost boundary

This is an explicitly selected live product experiment, not a new everyday test.
Keep it outside automatic regression discovery and reuse existing focused
acceptance. No new heavy regression, full-suite gate, or live inference in normal
developer checks. Disclose costly proposed follow-up tests before adding them,
under AGENTS.md; do not silently grow another expensive matrix.

## Completion record

The single planned run is recorded in [the dated report](../trials/routing-20260913/RESULTS.md)
and [sanitized machine evidence](../trials/routing-20260913/attempt-1.json).
App `019af67ac4671cf73b3f55e997359bf1ddc416e4`; task
`2b4ed33dc6174bbda46e06a6107cc714`. Full fixture/test/configuration hashes are
retained in both records. Operator-prepared plan; automatic remote selection.

Two included Kiro probes failed argument validation; one public-free OpenRouter
probe reported provider-wide daily quota exhaustion. Sibling routes were skipped.
No pair was selected, implementation began, checks ran, or receipts appeared.
Source/app/configuration/acceptance unchanged; no merge/push. Zero interventions.

31.604 seconds wall, 29.896 provider seconds, three requests, 13,296 accounted
tokens including an uncertain reservation. Included $0 marginal estimate is not
an invoice. No reviewer usage. Completion-quality counters stayed zero.

Next recommendation: an explicit required marker in the routing probe, keeping
strict argument validation, followed by one separately proposed same-fixture
trial. Raw returned arguments were not retained, so the omission's origin is
unproven. No live retry or new heavy regression added. Observer syntax/help and
diff checks pass; failure-report completion does not qualify automatic delivery.

Update this card and TASKS.md; commit only the sanitized experiment record.
