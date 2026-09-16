# T86 — Compact context without discarding the working approach

Status: Proposed — implementation not started
Depends on: T84, T85
Size: M/L
Context: [DeepSeek Harness assessment](../development/deepseek-harness-assessment.md)

## Outcome

Reduce oversized context while retaining intent, decisions, pending work, and a
recent complete conversation window. Older evidence stays retrievable.

## Implementation

1. Read `context_budget.py`, `context_compaction.py`, `check_output.py`, existing
   handoff excerpts, and the T85 record. Preserve route-aware capacity checks and
   the existing context-rejection recovery; do not add a turn-count reset.
2. First reduce duplicate snapshots and oversized tool output. Reuse existing
   check-output storage/retrieval; generalize only where another tool lacks it.
   Return a bounded preview with a task-scoped reference and a range/search
   retrieval operation. Retain source identity, omissions, and error content.
3. Compact an older complete range and preserve a recent complete assistant/tool
   window. Always retain active user constraints, unresolved approvals, and the
   T85 working state or a retrievable structured representation. Do not silently
   drop a constraint to make a request fit. Never split a call/result pair.
4. A checkpoint records intent, decisions, relevant files, resolved failures,
   outstanding work, and the next action, with references to original events.
   Reject applying a prepared checkpoint if its source range was replaced while
   it was being prepared; newer user input remains ordered and visible.
5. Begin with deterministic state and output pruning. If a model-generated
   summary is necessary, make its routing explicit through the existing gateway
   and authorization/accounting path. No hidden paid fallback or per-turn Gemma
   inference. Failed summarization retains the previous valid state and reports
   the actual capacity problem; it cannot erase work or claim a successful save.

## Acceptance

- A fixture whose decisive requirement occurs early still retains it after
  compaction, including a later correction that supersedes an earlier decision.
- A lost detail can be retrieved through its reference without rereading the
  whole project. Unavailable/expired references say so rather than invent content.
- Both default-limit and route-specific paths keep valid recent tool pairs.
- Summary text never grants authority or validates a check/reviewer receipt.
- Record before/after request size and retained evidence; fewer bytes alone are
  not a successful test if the next action loses necessary information.

## Validation and handoff

Extend existing compaction/context/check-output tests using in-memory transcripts,
temporary output artifacts, and a mocked summarizer if implemented. No network
inference or real-time waits in routine checks. Use change-scoped validation,
measure added-case runtime, and commit the implemented increment with limitations.
