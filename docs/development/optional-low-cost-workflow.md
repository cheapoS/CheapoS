# Deferred: an optional low-cost model workflow

Status: **design note only**, recorded September 13, 2026. Revisit after the
current T41–T48 milestones establish a useful, independently verified unattended
result and reliable routing evidence. This note does not authorize spending,
enable paid fallback, or change the current free-only setup.

## Why keep this idea

An inexpensive paid worker and a separate reviewer may reduce time spent waiting
for free capacity or recovering from unavailable routes. The hypothesis is worth
testing once cheapoS reliably completes work. Paid access alone cannot fix bad
tool arguments, repeated inspection, weak reviews, or orchestration bugs.

Success means a better **cost per verified, completed task**, with acceptable
elapsed time and fewer operator interventions. A cheaper token price or a faster
first response is not enough evidence.

## Possible operator choices

These are proposed supervised routing choices, not a description of controls
already available in the app. Manual provider/model configuration already exists.

| Choice | Intended behavior |
| --- | --- |
| Free only | Use eligible free routes and respect their quotas/cooldowns. Never switch to paid access because credits happen to be available. |
| Low-cost run | Operator explicitly selects priced access, approved models, and a task spending cap before starting. |
| Free first, approved paid fallback | A future optional policy permits priced fallback under a recorded cap. Without that authorization, pause and offer the choice. |
| Local participation | Operator chooses whether local hardware handles chat, implementation, or review. Do not silently move heavy work onto the laptop. |

The default remains free only. Purchasing credits to increase the free request
allowance is separate from authorizing paid inference; see the
[OpenRouter free-request allowance](../USER_GUIDE.md#openrouter-free-request-allowance).
Paid fallback authorization must have a clear scope and expiry, such as one run.
It must never increase its own cap or broaden the allowed model list.

cheapoS owns the decision to spend, the budget, task state, checks, and independent
review. OmniRoute owns connections and routing within that permission. A gateway
must be able to enforce the selected access policy and report the served model;
an unknown or unverifiable route is not an acceptable paid fallback. Review must
remain independent according to the task's review contract, even after a handoff.

## What to carry forward from the Gemini discussion

- **The credit threshold is useful, but balance is not purchase history.**
  OpenRouter bases the higher free request allowance on all-time credits
  purchased. A displayed balance alone does not establish that history. No
  account eligibility or task logs were audited for this note. See
  [OpenRouter limits](https://openrouter.ai/docs/api-reference/limits).
- **Timeouts need request-level evidence.** The current
  [stream parser](../../cheapos/streaming.py) defaults to 600 seconds at baseline
  `4e0b17d`. Other request deadlines and older versions may differ. The pasted
  claim about a 60-second watchdog does not establish the cause of a particular
  pause. Inspect the relevant version, route, error, and request timing first.
- **Paid performance is a hypothesis, not a guarantee.** Do not promise zero
  queuing, instant streaming, or 99.9% uptime. OpenRouter explicitly says its
  latency and throughput preferences do not guarantee those performance levels;
  see [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection).
- **Availability and price must be checked when implementing the workflow.**
  Do not turn the pasted model list into permanent defaults. A 404 needs the
  actual route and error inspected; it does not by itself prove why a model is
  unavailable. Use current catalog metadata, valid gateway IDs, tool capability
  checks, and observed outcomes from T46–T48.
- **Do not publish the “$15 buys 20,000 iterations” estimate.** It omits essential
  workload and pricing assumptions. Neither the quoted prices nor the listed
  models were revalidated for this note.

## Budget and interface requirements for a later implementation

Before starting priced work, show the allowed worker/reviewer routes, current
input and output rates, and an operator-chosen dollar cap. Explain when fallback
may occur. Keep the selected policy visible beside the conversation and show any
handoff in cheapoS's reply with its reason, route, and accounted cost.

Estimate token cost across **all requests**, not just the last worker response:

```text
estimated token cost = sum over requests of:
  (billable input tokens × input price per million
   + billable output tokens × output price per million) / 1,000,000
```

Use provider-specific rates for caching, reasoning tokens, or other charges when
applicable. Count worker and reviewer requests, repeated input context, and
billable probes/retries. Preserve reservations for requests whose final billing
is uncertain. Keep local usage and one-time credit purchase fees distinct from
inference charges, and label estimates separately from reported usage or an
invoice. A hard billing guarantee requires support from the provider/gateway;
do not present an estimate as one.

Refresh pricing before authorization and fail closed if a route's price or
identity cannot be established. Preserve saved work when the cap prevents another
request. Ask for a new authorization before increasing it. A paid handoff must
carry forward the same task context, patch, checks, and accounting rather than
silently starting over.

## Later experiment and exit criteria

Only after the current milestones, and after the operator explicitly authorizes
a priced trial:

1. Select a small coding task with an independently maintained acceptance check
   and a fixed starting snapshot. Use fresh task copies for a free run and a
   low-cost run on the same app version. Record the actual routes and limits.
2. Record verified completion, elapsed time, accounted/reported cost, retries,
   handoffs, reviewer outcome, and required operator interventions. Keep failed
   and paused attempts in the result; do not measure only successful requests.
3. Compare cost per completed task and time spent waiting or correcting errors.
   Treat the first pair as a pilot, not proof of general reliability or savings.
4. Propose actionable implementation cards only if the result warrants them.
   Preserve free-only operation and make any paid mode a deliberate choice.

Follow the existing [measurement policy](measurement-validation.md). Do not
disable approval, isolation, or accounting controls to make the comparison pass.
Keep future automated coverage focused on policy and accounting using synthetic
responses and injected clocks. Any new heavy test must be disclosed and accepted
under [CONTRIBUTING.md](../../CONTRIBUTING.md) before it is added. This document
adds no tests or live model runs.
