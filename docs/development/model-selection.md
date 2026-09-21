# Observed free-route selection

Eligibility is always checked against the current catalog, explicit free pricing,
tool capability and cooldown. Existing eligible placements stay pinned; manual and
local choices do not enter automatic selection. An automatic reviewer cannot be a
current or former patch author.

For each endpoint/model, retain at most 64 role/run observations from 30 days,
within the existing 2,000-record bound. IDs are hashed; no outputs or prompts are
stored. Worker checkpoint submissions and reviewer completed decisions are
protocol outcomes, not proof of correctness. Successful file/web calls, edits,
checks and explicit operator commit acceptance remain separate counters.

Configured preferences lead automatic ranking. Independently validated and
disproved completions, recorded completions, role outcome tiers and human
acceptance precede response/tool compatibility and catalog hints. At least three
run samples are needed to change an outcome tier; repeated invalid outputs can
demote a model. Worker checkpoints and accepted plans can inform those tiers;
reviewer approval by itself is not independently validated correctness.
Provider interleaving operates within equal evidence/prior tiers and cannot
move a benchmark above observed results. Provider/account cooldown and recovery
diversity still govern availability before dispatch.

### Catalog benchmarks

The existing [OpenRouter model catalog](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties)
can supply Artificial Analysis coding, agentic and intelligence indices. cheapoS
retains recognized finite, nonnegative numeric scores, their source, catalog and
UTC refresh timestamp. No new service or inference request is needed. OmniRoute's
existing OpenRouter free-catalog refresh carries this metadata onto the exact
`openrouter/` route ID. Other gateways may supply the same benchmark fields.
There is no model-name matching or transfer of scores between aliases/routes.

After operator preferences, observed outcomes and compatibility, automatic
workers and reviewers prefer the coding index; planners prefer the agentic
index. The intelligence index is displayed only. This is an initial prior, not
proof of task quality. Missing or malformed scores remain unknown; zero is a
real reported value. Scored candidates lead unscored candidates within otherwise
equal evidence tiers, but no model is excluded for lacking scores. Stale metadata
does not contribute a benchmark preference. Name/capability hints, observed
response latency and model ID resolve remaining ties. Name and size are not
measured quality; latency is not end-to-end task time. Conversation-only routing
continues to use observed responsiveness rather than coding benchmarks.

Settings → Connections → Authorized remote model pool shows these scores alongside
local outcome evidence. Optional coding/agentic sorting changes the view only, never saved
agent choices or authorization. Its default remains catalog order, and unknown
scores sort last without disappearing. The refresh date is when cheapoS fetched
the catalog, **not** the date the benchmark was run. A refresh replaces missing
scores rather than silently retaining old ones, and never resets local failures.
Catalog benchmarks are not signed cheapoS request/completion evidence and are
not exported as public task statistics.

Outages only affect availability cooldown, and cancelled runs do not contribute
quality samples. Provider cooldown remains shared availability state. Legacy
records retain their cooldown and compatibility evidence. A successful tool probe
may be reused for five minutes after all current eligibility checks; reuse does
not renew that timestamp or consume a probe. A failed observation prevents reuse.

Models displays role sample counts and observed counters. The deterministic T24
fixtures replay actual controller events into these observations and verify
separate operator acceptance. They cannot establish real-model coding quality.

### Dedicated planning

Connections offers an optional expandable **Use a dedicated planner** choice.
When disabled, planning inherits the saved reviewer connection and credentials.
Selections apply to new proposals; saved proposals retain their provider policy.
Saving other roles preserves an existing planner; explicitly disabling it resets
fallback. Endpoint/model choices survive restart. Direct-provider keys remain in
memory or their CHEAPOS_* environment variable, never configuration/task JSON.
Automatic remote placement still admits only authorized free/included models;
selecting a stronger planner does not authorize paid escalation. Local execution
has an optional installed local planner preference and never downloads on save.
