# T25 — Rank free models using observed completed work

**Depends on:** T24. **Size:** M. **Result:** automatic selection prefers evidence of useful performance over catalog order or model branding.

## Read first

`model_pool.FreeModelPool` record/rank/cooldown logic, `routing.select_remote`, provider catalog refresh/retirement handling, and T24 metric definitions.

## Implementation

1. Extend observations with role-specific outcome signals that are actually known: valid tool calls, successful edits/checkpoint submission, review completion, latency, invalid-output failures, and operator-accepted task outcomes. Keep sample count and last observation time.
2. Do not equate reviewer APPROVE with independently correct code. Distinguish a worker's invalid tool call from a provider outage or operator cancellation. Do not penalize every model for a shared provider cooldown.
3. Define a small deterministic ranking policy with documented tie-breaking, minimum evidence thresholds, recency, and bounded history. A success history can help; it cannot override current ineligibility, unknown/paid price, missing capability, retired catalog entry, or cooldown.
4. Keep a working eligible pair sticky across the appropriate task stage. Avoid repeated probes when a current valid observation suffices. Worker and reviewer remain distinct where the execution mode requires it; manual/all-local choices stay fixed.
5. Show a compact explanation in Models/Details, such as valid-tool history or recent failures, with sample size. Do not invent a universal quality score from model name, parameter count, or one trial.
6. Migrate old health records without losing cooldowns. Metrics must not store model outputs or secrets.

## Acceptance

Given fixture histories, ranking is deterministic and a repeatedly invalid model ranks below a proven eligible alternative. Sparse history falls back sensibly. A retired/cooling/paid model is never selected despite old successes. Cancellations and provider outages do not corrupt model-quality statistics. Manual/local placement and distinct-reviewer tests still pass.

## Validation / limits

Run pool/routing tests and replay T24 fixture observations. No automatic paid escalation, aggressive probe load, opaque learned ranker, or changing a live manual model. Do not claim improved coding quality until real repeated trials support it.

## Completion record

Status: Todo

- Behavior delivered: —
- Acceptance evidence: —
- Commands and results: —
- Browser scenarios and results: —
- Remaining limitations: —

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
