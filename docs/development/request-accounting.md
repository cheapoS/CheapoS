# Request pacing and reserved tokens

## Reported usage and local reservations

The session total is an **accounting total**, not necessarily measured model
consumption. Session details now separate reported tokens from retained
reservations and show the unresolved requests behind those reservations.

Before dispatch, `providers.reserve` records this conservative estimate:

```
prompt estimate = UTF-8 byte length of serialized messages and tool schemas + 1,024
reservation = prompt estimate + output allowance
```

Bytes are deliberately counted one-for-one for budget preflight; this is not a
model tokenizer. The buffer accounts for additional framing uncertainty. The
output allowance normally comes from the task's output limit; probes are capped
at 1,024 and coordinator requests at 512. Reviewer and spending limits can reduce
that allowance. Measurement mode can omit the actual provider output cap on
zero-rate requests, so its reservation is an estimate, not a guaranteed upper
bound. New request records retain the byte count, buffer, and formula version.
Older records still expose their saved prompt/output estimates without inventing
missing formula metadata.

Complete, valid provider input/output counts replace the estimate. This also
applies when a failed response carries valid usage. A timeout, cancellation,
missing usage, or HTTP rejection without usage retains its reservation. The
request might have reached an upstream model, and a gateway can have made several
attempts. A failed request does not by itself establish zero consumption.

Reservations are **local budget bookkeeping**, not funds held by OmniRoute or a
provider. A free request can have a large token reservation and a $0 cost
reservation. Input, output, cached, and reasoning counts must not be added as
independent categories: cached/reasoning counts can be subsets.

The public breakdown is read-only and excludes prompts, endpoints, credentials,
and raw provider bodies. Partial/truncated historical records remain explicitly
partial. The latest 50 unresolved request rows are shown; totals include all
available reservation records. This view does not reset budgets or alter lifetime
accounting.

## Example: a planning run stopped on September 17, 2026

The session displayed **233,066 accounted tokens**:

| Evidence | Tokens |
| --- | ---: |
| Complete usage reported by successful requests | 133,422 |
| OpenRouter planning request: 86,454 prompt estimate + 8,192 output | 94,646 |
| NVIDIA connection probe: 1,475 prompt estimate + 1,024 output | 2,499 |
| OpenCode connection probe: 1,475 prompt estimate + 1,024 output | 2,499 |
| Total retained reservations | **99,644** |

The planning reservation came from 85,430 serialized bytes + the 1,024 buffer +
8,192 output allowance. Each probe used 451 bytes + 1,024 buffer + 1,024 output.
The three failed calls returned no complete usage counts. Their real consumption
is unknown; the 99,644 is not a claim that the models consumed that many tokens.

## Which layer retries?

CheapOS makes model requests sequentially within a planner run, including file
inspection turns, proposal attempts, and connection probes. File reads themselves
are local tools; asking the planner what to do after a read is another model
request. Repairing an invalid proposal resends the accumulated context. Even a
short repair response can therefore carry a substantial input payload.

`request_pacer` spaces calls by upstream provider. Larger serialized payloads
receive extra quiet time, including Groq requests. This smooths traffic; it does
not know an account's exact token-per-minute quota and cannot guarantee that a
request fits. Provider cooldown and retry hints remain authoritative.

OmniRoute can make several upstream attempts during one CheapOS request. In the
example above, one OpenRouter call took about 41 seconds at the gateway and
included four upstream 429 responses. CheapOS could not select another provider
until that call returned. Client pacing cannot space retries hidden inside the
gateway.

For an OmniRoute instance where CheapOS manages recovery, use **Settings →
Resilience → Wait For Cooldown → Enable server-side wait: Disabled**. This returns
that cooldown failure to CheapOS sooner so its authorized routing policy can
select another eligible provider or schedule a wait. It preserves connection
cooldowns and circuit breakers; do not disable those protections.

This is a gateway-wide preference affecting other clients. There is no supported
per-request override in the inspected OmniRoute 3.8.50 handler. Combo retry
settings and provider-specific transport retries are separate; disabling this
wait is not a guarantee of exactly one upstream attempt in every gateway path.

During this investigation the local gateway setting changed from enabled
(three attempts, up to 30 seconds each) to disabled. No provider credentials,
access permissions, spending policies, or combo settings were changed. A live
inference trial was not run as part of validation.

## Proposal repair

Unknown fields now identify their exact plan/item location in validation
feedback. Valid assumptions misplaced inside `plan` are normalized to the
supported assumptions field and retained in item instructions. Invalid or
excessive assumptions remain errors. Model-supplied changes to authorized
limits remain rejected, with the differing fields named. This reduces avoidable
repair turns without widening execution authority.

## Patch validation

Focused validation covered proposal parsing and repair, pacing, budget accounting,
public pause explanations, and the existing engine failure/resume safeguards:
118 Python tests passed (two selections: 2.28s and 14.52s). All 240 JavaScript
checks passed in 0.20s. The eight new Python cases took 0.034s including their
first imports; the three new JavaScript cases ran in a 0.078s process. These
regressions use in-memory records and parsing, not new full agent/Git workflows,
provider calls, or deliberate waits.

An isolated localhost server with synthetic records returned the expected
reported/reserved split through the real task API. Chrome blocked the temporary
preview with `ERR_BLOCKED_BY_CLIENT`, so a visual browser check of that fixture
could not be completed. After the idle app was restarted, a read-only inspection
of the existing saved session verified the header, role totals, and expanded
three-request breakdown in the real UI. Its task remained paused. No live
inference or retry trial was performed.
