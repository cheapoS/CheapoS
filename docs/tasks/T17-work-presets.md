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

Status: Todo

- Behavior delivered: —
- Acceptance evidence: —
- Commands and results: —
- Browser scenarios and results: —
- Remaining limitations: —

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
