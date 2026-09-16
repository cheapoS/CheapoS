# A more continuous cheapoS agent loop

Assessment: September 15, 2026. Status: source review and proposed implementation
plan; no harness migration or live comparison has been performed.

## Recommendation

Adopt DeepSeek Harness's continuous-session approach incrementally. cheapoS should
retain the user's intent, discoveries, decisions, unfinished work, and tool
results while it implements, recovers, receives feedback, and changes models.
An operator should be able to say “continue” and see the next supported action
from that saved state, or a concrete explanation of the decision still needed.

The current architecture has useful foundations: isolated workspaces, exact
verification receipts, independent review, explicit spending authorization,
provider recovery, and visible work. Keep those. Make the agent's implementation
path more flexible and give it a consistent view of its work.

Do not replace the Python engine with DeepSeek's TypeScript/Cordis runtime as the
first step. That would require adapting cheapoS's existing routing, accounting,
permissions, review, and Git contracts before demonstrating better completion.
Borrow the design and evaluate individual components after the behavior improves.

This milestone is a consolidation of the execution loop. Every replacement must
identify and retire its superseded decision path; adding another recovery prompt
or counter beside the existing ones is insufficient. Preserve saved-task
compatibility through an explicit adapter, with one authoritative representation
for new work. The product should not require several controllers to independently
guess the next step from different excerpts of the same conversation.

The target loop is straightforward:

```text
Accept and persist operator input
  -> assemble the continuing conversation and current working state
  -> request the next model action
  -> validate authority, execute permitted tools, persist actual results
  -> continue from those results
  -> answer, request a real decision, or submit a completed candidate for review
```

The reviewer has its own evidence-bound session. Its findings return to the
existing worker session as new information. The engine owns authorization,
accounting, execution receipts, and completion checks. The worker chooses how to
implement the authorized request using that information. Ordinary progress does
not need another model or another controller invocation after every step.

## What was inspected

- DeepSeek Harness at `0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`:
  agent-loop implementation, session history, compaction implementation, todo and
  goal continuation packages, output spill storage, architecture, and license.
- cheapoS at `16b6c44a926c6a56fdc5dcc869e59635283a0aba`, plus the working tree.
  Engine/provider/reviewer changes were already uncommitted and changing during
  this review. They are not part of this documentation change, and this review
  does not certify them. Reconcile those changes before implementing the cards.
- This is source evidence, not a replay of the user's failed tasks. The findings
  identify credible failure mechanisms; they do not prove the cause of every
  observed loop, provider interruption, or incomplete feature.

DeepSeek labels the project a rapidly changing developer preview. Its repository
uses MIT licensing; copied substantial portions need the required notice, and
any imported component needs its own dependency/third-party notice review.
Source availability does not establish production reliability. See its
[README][upstream-readme] and [license][upstream-license].

## The useful differences

| Upstream design | Benefit for cheapoS | Adoption boundary |
| --- | --- | --- |
| A durable session log supplies each next model request | Recovery and model handoff continue an existing investigation | Start with a shared conversation builder over existing saved records; a new storage framework is unnecessary |
| A model step includes its tool results; ordinary tool work leads to another step | A transient failure need not restart the task or replay completed actions | Keep attempts, tool execution receipts, and accepted assistant messages distinct |
| Compaction retains a recent complete exchange window and summarizes older work with intent, decisions, errors, pending work, and next action | The next model can resume an approach instead of rediscovering it | Preserve original evidence; a summary is not proof of permission, checks, or completion |
| Session-owned todos and a durable goal | Both operator and worker can see what remains | An implementation checklist cannot modify the operator-approved unattended plan |
| Oversized results become previews with retrievable references | Reduce repeated context without losing access to useful evidence | Extend existing check-output retrieval; keep task ownership and redaction |
| An optional same-session goal driver continues unfinished work | Routine continuation can happen without a human inventing a prompt | Respect Pause, authorization, spending and explicit limits; upstream also has continuation boundaries |

Sources: [agent loop][upstream-loop], [session][upstream-session],
[compaction implementation][upstream-compaction], [summary implementation][upstream-summary],
[todos][upstream-todo], [spill storage][upstream-spill], and
[goal continuation][upstream-goal]. These are design observations, not benchmark
claims. Upstream's plugin system, parallel tool scheduler, browser tools, and
other capabilities can be evaluated later; importing all of them is not the
current milestone.

## Specific cheapoS findings

### Continuity is partially implemented, but inconsistent

[worker_conversation.refresh()](../../cheapos/worker_conversation.py) already
preserves worker exchanges and closes interrupted tool envelopes. The normal
start and several recovery/handoff paths use it. It would be inaccurate to say
cheapoS erases the entire conversation after every tool call.

However, `BranchController.continue_item()` in
[branch_controller.py](../../cheapos/branch_controller.py) assigns
`task['messages'] = self.engine.initial_messages(task)` before worker continuation,
including after a resumed review returns REQUEST_CHANGES. The committed baseline
has this behavior too. The source-commit path in
[engine.py](../../cheapos/engine.py) clears `messages` before awaiting the next
user reply. Some explicit reconciliation/operator revision paths reset it as well.
These boundaries have different purposes; inspect each rather than preserving
stale authority indiscriminately. Prior conversations should remain available as
history even when their checks or approvals are no longer current.

### Saved context is not yet a specific working plan

[project_context.continuation()](../../cheapos/project_context.py) retains user
requests and evidence, but `remaining_requirements` is a generic instruction to
evaluate all requirements, and `next_step` is often generic too. Its file samples
are the first 30 lines / 1,000 characters of up to eight files. Other handoff
paths already preserve relevant ranges; reuse those improvements.

The gap is a durable record of the actual approach: what was learned, what was
ruled out, what remains, and which evidence supports the next action. A directory
listing, last error, and patch do not fully communicate that state.

### Compaction can retain facts while losing the thread of the work

[context_budget.py](../../cheapos/context_budget.py) already triggers ordinary
compaction based on route capacity; do not reintroduce a fixed periodic reset.
[context_compaction.py](../../cheapos/context_compaction.py) preserves recent
claims and completed actions, but builds much of its summary from bounded
excerpts: three assistant statements, four completed edit/check actions, and
truncated fields. Some modes retain complete recent exchanges. This is better
than an empty restart, but it can omit an earlier decision or unresolved step.

Extend the existing machinery with an explicit working state and retrievable
history. Do not simply send the entire transcript forever or run a local
summarizer on every turn.

### Productivity heuristics can steer too aggressively

[progress.py](../../cheapos/progress.py) recognizes changes to patches, checks,
review decisions, and completed answers. New inspection evidence is not itself
part of that progress counter. This can disadvantage legitimate exploration;
it does not mean every repeated read is useful or should reset an allowance.

[work_policy.small_edit_reason()](../../cheapos/work_policy.py) can switch to
compact editing after a file observation exceeds 200 lines or 6,000 characters.
The engine then substitutes line/compact-write tools for the normal edit tools.
That can be a useful compatibility fallback, but a file's size alone is weak
evidence that the worker needs a different editing workflow.

The engine also inserts wrap-up guidance near a checkpoint interval. It already
has soft continuation and measurement behavior, so this is not universally a
forced checkpoint. Nevertheless, time/turn hints, stage hints, compact-edit
guidance, review feedback, and coordinator advice can compete. Consolidate their
ownership and measure which interventions help completion.

## Desired operator experience

For “implement a real backend restart,” the conversation should retain a small
working checklist: inspect restart lifecycle; implement endpoint; connect UI;
verify; resolve independent review; await the authorized integration decision.

When verification passes, cheapoS should show that evidence and continue to
review. If review finds a missing startup check, the worker receives the exact
finding alongside its previous implementation context and fixes that gap. A
provider failure preserves this position. The next authorized route continues
with the existing check receipt when it is still valid.

“Continue” should select a concrete eligible action and show it immediately.
If it cannot run, explain the actual blocker and give the relevant control.
Do not require a magic sentence, invent missing requirements, silently reset
exhausted spending, or claim a saved message has been dispatched when it has not.

Live output, current action, checklist progress, verification, and review belong
inside one cheapoS reply. Show model identity and handoffs in Details. Keep
technical attempt logs separate from ordinary conversation history. The optional
local coordinator remains idle until an eligible intervention needs it.

## Implementation order

1. [T84: preserve session continuity at transitions](../tasks/T84-session-continuity.md).
2. [T85: persist a specific working state and checklist](../tasks/T85-working-state.md).
3. [T86: improve compaction and evidence retrieval](../tasks/T86-context-continuity.md).
4. [T87: consolidate recovery and relax unhelpful pacing](../tasks/T87-continuation-policy.md).
5. [T88: qualify completion and the operator experience](../tasks/T88-harness-qualification.md).

Implement one card at a time. Start with continuity; adding another coordinator
prompt before fixing what context reaches it risks repeating the same failure.
The end-to-end criterion is completion with fewer unnecessary requests and fewer
operator interventions, not fewer pauses obtained by weakening review.

Keep monetary and access policy, command permissions, candidate-bound review,
Git isolation, operator Pause, and explicit scope boundaries enforceable. Treat
editing style and progress hints as adjustable assistance. A passing test is
evidence about that test, not proof that the requested feature is complete.

## Qualification limits

No upstream code was executed, no live model requests were made, and no runtime
settings were changed for this assessment. Use existing deterministic fixtures
for small regression cases. No new heavy agent/Git workflows or timed waits are
authorized by these cards; disclose cost and obtain acceptance before adding one.
Future live comparisons require explicit model/spending authorization and
measurement mode. Compare identical task requirements and acceptance evidence,
record failures and interventions, and do not present a changed-model comparison
as a harness-only improvement.

[upstream-readme]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/README.md
[upstream-license]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/LICENSE
[upstream-loop]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/core/agent-loop/src/agent.ts
[upstream-session]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/core/session/README.md
[upstream-compaction]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/compaction/compaction-basic/src/region.ts
[upstream-summary]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/compaction/compaction-basic/src/summarizer.ts
[upstream-todo]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/todo/tool-todo/src/index.ts
[upstream-spill]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/spill/spill/README.md
[upstream-goal]: https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/goal/goal-round-driver/README.md
