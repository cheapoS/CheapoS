# Provider pacing and cooldown handoffs

Three different waits can look like a slow model handoff:

1. **Client pacing:** `PROVIDER_PACING_SECONDS` sets local quiet intervals after
   a request completes. Calls to the same upstream provider share a slot across
   models and roles. Different upstream providers behind OmniRoute do not share
   that slot. Payload scaling remains unchanged. These intervals smooth traffic;
   they are not a token-per-minute limiter or a guarantee against rate limits.
2. **Route cooldown:** a rate/quota response makes the affected model, provider,
   account, or connection temporarily ineligible. Automatic routing checks other
   eligible candidates within the saved access policy. If none is available,
   the existing cooldown wait applies. A quota error does not lower model quality.
3. **Gateway retry:** one CheapOS request can contain several upstream attempts
   made by OmniRoute. CheapOS cannot choose another route before that request
   returns. Local pacing does not control those hidden attempts.

Repeated cooldowns now retain a persisted streak at their original scope and
connection revision. The first delay uses Retry-After when available, otherwise
120 seconds. Consecutive cooldowns double that base, with a 15-minute ceiling on
the locally increased delay. A longer upstream delay still wins, subject to the
existing 24-hour normalization limit. A newer short response cannot shorten an
already retained deadline. For a repeated 24-second Retry-After, delays are
24, 48, 96, 192 seconds, and so on.

A tiny successful tool probe establishes tool compatibility; it neither clears
an active cooldown nor resets the streak. Only an actual non-probe response
resets its model streak. It also resets an expired shared provider/account
streak, without clearing an active shared cooldown. This prevents a repeating
cycle of successful tiny probe, rejected full prompt, and immediate re-selection.
Resume, catalog refresh, and app restart do not erase the saved streak.

During automatic availability recovery, a different eligible provider takes
priority over cached probes and model preferences on the affected provider.
Selection also reorders remaining candidates after a probe reports a cooldown,
transport failure, unavailable route, or candidate rejection. This preference
does not mark healthy sibling models broken: they remain fallback candidates if
other providers cannot respond. Existing access, tool capability, context fit,
reviewer independence, and scoped cooldown exclusions still apply. No additional
probe allowance is granted. The activity stream explicitly says **Trying another
provider** at this transition.

This is temporary ordering for the current selection, derived from its failure
and current pool observations, not a permanent provider ban. A saved legacy
provider-exclusion list cannot prevent a recovered provider from being selected.

## September 16 investigation

Saved request records showed selection of the next candidate beginning roughly
0.05–0.1 seconds after the cooldown event, but individual planning calls took
about 50 seconds to return and some replacement probes took about 45 seconds.
The old metrics included local pacing in that duration, so they cannot precisely
attribute all elapsed time to the gateway.

The installed OmniRoute source contained both same-endpoint 429 retries and
cooldown wait/retry handling. Its default retry settings do not prove what the
operator's saved settings were. Several red upstream request rows can therefore
correspond to a single CheapOS request; the dashboard alone does not establish
which layer initiated every attempt.

New request records include `pacing_seconds` and `gateway_request_seconds`, on
success and failure, to distinguish local queue delay from the HTTP wait. They
do not reveal individual gateway attempts or upstream-only latency. No gateway
retry setting, model authorization, spending limit, or request timeout was changed
by this fix. A gateway policy that returns quota failures promptly is a separate
integration decision, particularly when other applications share that gateway.

## Focused validation

Use the existing request pacer, model pool, route health/schedule, cooldown wait,
routing, transport/streaming, gateway, credential and admission modules. New
regressions use fake clocks, mocked HTTP responses and a bounded thread rendezvous;
they perform no live inference or deliberate real-time cooldown waits. They cover
probe/backoff persistence, deadline preservation, independent provider slots,
queue cancellation, and timing on both successful and failed HTTP responses.

On September 16, the 12 focused modules ran 169 cases in 29.396 seconds. Two
loopback cases initially blocked by the filesystem/network sandbox passed when
rerun with local socket access. Result: 168 passed; the remaining transport
case, `test_tolerance_does_not_override_lower_task_budget_or_missing_usage`,
also failed on an isolated copy of the unchanged `ccc853f` baseline. It expected
a budget error for incomplete usage but received `ProviderError`. No assertion
or accounting rule was changed here. The six new/updated regression cases took
0.011 seconds together; no heavy test was added. The full suite and live inference
were not run for this change.

The follow-up provider-selection fix passed 96 existing and new focused cases
across routing, pool, health, probe rejection, schedule, cooldown waits,
connections and access policy in 28.309 seconds. Its two new injected-state
regressions took 0.016 seconds together and reproduce cached/preferred sibling
starvation, immediate rotation after a failed probe, and same-provider fallback
when another provider fails. The existing real worker/reviewer handoff test also
passes with the new selection order. No live model request was sent.
