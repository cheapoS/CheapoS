# T15 — Bounded recovery and actionable pause explanations

**Depends on:** T14. **Size:** M. **Result:** the controller tries a small justified repair before asking the operator to click Resume.

## Read first

Existing repeated-read guard, action/output/compact recovery, `model_pool.py`, persisted pending checkpoints/reviews, and guidance error rendering. Read the existing recovery tests before adding another recovery path.

## Implementation

1. Define progress evidence in one helper: changed useful patch, completed new check, resolved failure, answered question, or advanced remaining task step. Repeated same reads, cosmetic message changes, and flipping a file back and forth must not indefinitely count as progress.
2. On a recoverable stall, use the existing saved evidence to issue one specific correction: answer from current evidence, use a small edit, fix the reported check, or submit the current complete patch. Do not replay malformed responses.
3. Reuse existing automatic free-model handoffs only when task mode permits and the configured recovery allowance remains. Manual/all-local keep their chosen model. Refusal, auth/credit errors, missing required usage, user stop, and hard limits retain their distinct behavior.
4. Persist the recovery attempt count/state through Resume and process interruption as appropriate, scoped to the user request. A new user request may start a new work segment, but must not reset cumulative financial/time accounting.
5. After bounded recovery fails, produce one actionable pause summary: what was attempted, current saved files/checks, exact blocker, and the smallest decision or information needed. Do not ask for a hash CheapOS already tracks or suggest identical retries without a changed condition.
6. Show short recovery updates inside the CheapOS reply; keep full diagnostics under Details. Preserve pending reviewer work so recovery does not repeat implementation or passing verification unnecessarily.

## Acceptance

Fixtures cover repeated read, malformed edit, output truncation, failed test, reviewer revision, unavailable allowed handoff, and irrecoverable missing information. Each either progresses within its allowance or stops once with an accurate reason. Repeated Resume without changed input cannot create infinite new recovery allowance. Saved work and usage remain intact.

## Validation / limits

Extend the existing answer/output/compact/model-pool recovery modules rather than replacing the engine loop. Record a browser example of successful recovery and one informative pause. No invented progress animation, hidden local/paid fallback, bypassed checks, or model-generated declarations used as proof of success.

## Completion record

Status: Todo

- Behavior delivered: —
- Acceptance evidence: —
- Commands and results: —
- Browser scenarios and results: —
- Remaining limitations: —

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
