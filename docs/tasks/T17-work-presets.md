# T17 — Simple working-time and spending controls

**Depends on:** T14, T16. **Size:** M. **Result:** operators choose a useful work envelope without understanding eight overlapping counters.

## Read first

Limits parsing/defaults/preferences, `chatLimits`, resume actions, execution choice UI, and current free-only/provider accounting behavior.

## Implementation

1. Present the primary controls as `Free only` (or the explicit dollar cap) and a working-time preset: Interactive or Extended. Show the actual chosen duration in plain text. Keep technical counters under Advanced.
2. Establish documented conservative preset values based on existing limits and T14/T16 behavior. A preset is an explicit user change, not an engine excuse to increase a saved task's budget. Keep all values within validated bounds.
3. Distinguish defaults for new chats from limits on the current chat. Changing defaults must not silently rewrite a running task or its providers. Keep saved custom values visible as Custom.
4. Ordinary Pause → Resume uses current settings without opening a modal. A hard-budget stop opens the specific relevant limit with used/remaining amounts, rather than asking the operator to rediscover which counter fired.
5. Explain that a work-time limit and a check timeout differ, without requiring both as normal setup fields. Show meaningful usage near the task; move technical reservations/details out of the primary conversation.
6. Preserve paid-model opt-in and local-only placement. Free-only accounting is not a provider billing guarantee; give one concise settings explanation rather than repeated warning cards.

## Acceptance

Switch new-chat defaults, create a chat, customize it, pause/resume, hit a hard limit, and continue after an explicit adjustment. Existing chats keep their prior values. Free-only never becomes a positive cap from a preset. Extended has a real bound and working Pause; the UI does not promise unattended reliability that has not been tested.

## Validation / limits

Add limits/preferences serialization and UI-state tests. Browser-test preset/custom modes and hard versus ordinary pauses. No removal of backend caps, unbounded mode, hidden purchase/upgrade, or reset of cumulative usage.

## Completion record

Status: Done

- Behavior delivered: Free only or explicit cap plus Interactive (15 minutes/40 turns/5 iterations) and Extended (45 minutes/120 turns/10 iterations). Nonstandard work/check/token settings display Custom. Presets preserve spending and placement. Advanced holds technical counters. Separate new-chat defaults and current-chat limits. Specific structured hard-limit usage opens only the relevant adjustment; ordinary Pause/Resume uses current settings.
- Acceptance evidence: Defaults/current-task serialization and restart isolation tests, specific spending/reviewer-token preflight information, working-time stop classification, and pure preset tests preserving zero/positive spending and custom advanced values. Free-only accounting and existing recovery remain bounded.
- Commands and results: Engine/boundary/cooldown/verification: 38 passed (40.505s). New work-limits tests: 3 passed (1.198s). HTTP and output recovery: 36 passed (39.362s). JavaScript syntax, 66 presentation tests and diff checks passed. Logs /tmp/cheapos-t17-*.log.
- Browser scenarios and results: Changed defaults to Extended while an existing task stayed Interactive. Customized it to 22 minutes; ordinary Pause/Resume used Custom 22 without a modal. Hard worker stop showed Used 1 of 1; adjusted only turns to 2 and continued. A newly created task inherited Extended 45/120/10 and zero dollars. Verified stored fixture limits. Narrow dialog remained scrollable and Save was keyboard-reachable; viewport reset afterward.
- Remaining limitations: Presets are bounded work envelopes, not a reliability promise. Advanced overrides intentionally keep Custom even when the duration matches a preset. Nonadjustable accounting/model/patch blockers direct the user to the specific evidence instead of increasing unrelated limits. Free-only depends on configured prices; provider billing remains separate.

Before implementing, read [TASKS.md](../archive/TASKS.md) for the shared contract. Update this record and the matching board row when complete.
