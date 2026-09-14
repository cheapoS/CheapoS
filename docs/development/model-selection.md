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

At least three run samples are needed to change a ranking tier. Three or more
checkpoint/review completions with no invalid outputs promote a role; three or
more invalid outputs exceeding completions demote it. Otherwise the tier is
neutral. Ties use configured preference, capped human acceptance, observed
response/tool compatibility, reviewer capability metadata, observed response
latency, then model ID. Model size/name is not a quality score. Latency is the
existing role response moving average, not end-to-end task time.

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
