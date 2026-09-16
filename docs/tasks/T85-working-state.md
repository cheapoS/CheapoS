# T85 — Give the agent a durable, specific working state

Status: Proposed — implementation not started
Depends on: T84
Size: M
Context: [DeepSeek Harness assessment](../development/deepseek-harness-assessment.md)

## Outcome

The worker and operator can answer: What are we trying to achieve? What have we
learned? What is unfinished? What happens next? Recovery uses those answers.

## Implementation

1. Read `project_context.py`, `recovery_context.py`, `execution_context.py`,
   `coordinator_dispatch.py`, existing branch plan storage, and the conversation
   presentation helpers. Extend an existing continuation record where practical.
2. Store a versioned, task/item-owned working state: current objective, ordered
   user corrections, implementation steps with stable IDs, decisions/rationale,
   relevant file/range references, unresolved findings, pending actions, and a
   concrete proposed next action. Link observations to their source event and file
   version. Separate model claims from engine-verified action/check receipts.
3. Give workers a small validated update mechanism. An implementation checklist
   is advisory and may evolve inside the accepted scope; it must not rewrite the
   unattended plan, grant permissions, mark a reviewer approval, alter routing,
   increase spending, or complete the controller's job. Skip a checklist for a
   trivial answer instead of forcing unnecessary tool calls.
4. Reuse this record for handoff, compaction, resume, and optional coordinator
   consultation. Update at meaningful transitions, not through a local-model
   polling loop. Keep exact user intent available even if summaries omit prose.
5. Show current step and concise progress inside the owning cheapoS reply, with
   Details for history. Preserve open Details, drafts, and normal scrolling.
   Make pending approval, paused, and executing states visibly different.

## Acceptance

- After a simulated restart, the next request includes a specific unfinished step
  and the latest correction, not just “evaluate all remaining requirements.”
- The example restart feature retains endpoint, UI, readiness, verification, and
  review work through a rejection; completed work is not silently reopened.
- Checklist completion does not mark task/check/review completion. Stale source
  observations remain labeled and can be refreshed with targeted reads.
- An approved unattended scope cannot be expanded by the checklist tool.
- No local coordinator inference runs unless an existing eligible consultation
  is requested. This feature works without a coordinator.

## Validation and handoff

Use small serialization/projection tests and existing conversation DOM fixtures;
exercise one disposable UI transcript through working, review, and paused states.
Use the change-scoped selector and record timings. New live trials, long waits,
and full agent/Git fixtures require separate cost acceptance. Commit the card and
record implementation limitations honestly.
