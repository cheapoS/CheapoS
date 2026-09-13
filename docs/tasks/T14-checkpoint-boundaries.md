# T14 — Make checkpoint turn intervals internal scheduling boundaries

**Depends on:** T13. **Size:** M. **Result:** useful work can cross the twelve-turn checkpoint interval without automatically requiring Resume, while hard outer limits still hold.

## Read first

`Runtime`, `DEFAULT_LIMITS`, run-loop turn accounting, loop guidance, checkpoint handling, `tests/test_routing.py`, `test_answer_recovery.py`, and `test_review_workflow.py`.

## Implementation

1. Explicitly distinguish a soft checkpoint interval from hard overall worker turns, working time, monetary/token caps, and review-round bounds. Preserve old saved settings and their interpretation through a documented migration/default policy.
2. At a soft boundary, inspect durable state deterministically. A question with enough evidence should request its concise answer. A worker that declared completion with edits should enter verification/review. Incomplete work with demonstrated progress may compact context and continue to the next bounded interval.
3. Do not label a partial patch as finished simply because a timer/counter fired. Reuse the existing final-answer/checkpoint completion signals; review against all user requirements. An intermediate checkpoint does not authorize a commit or erase unfinished scope.
4. Reset only the local interval counter when continuing. Keep overall turns, elapsed time, accounting, failed recovery attempts, and review iterations. Every model call counts.
5. Record a compact controller event such as `Saved progress; continuing the remaining step`, visible inside CheapOS Details. Do not add a new model conversation to decide whether to continue.
6. If there is no meaningful progress or no remaining hard allowance, hand off to the existing pause/recovery mechanism with a specific reason. T15 improves that recovery next.

## Acceptance

A scripted implementation needing thirteen useful turns under a forty-turn hard allowance continues through the soft boundary and reaches real checks/review. A non-progressing loop still stops. A hard time/dollar/turn stop is never extended. Questions are not forced into code changes. Partially completed user requirements never get a ready-to-commit UI only because an interval ended.

## Validation / limits

Add boundary tests using short scripted runs and fake/injected clock where suitable. Keep stop, budget, and accounting tests passing. No unlimited turns, automatic increases to budgets, paid-model escalation, or broad model-policy changes. Do not use counter resets to conceal total work.

## Completion record

Status: Todo

- Behavior delivered: —
- Acceptance evidence: —
- Commands and results: —
- Browser scenarios and results: —
- Remaining limitations: —

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
