# T84 — Preserve the conversation through task transitions

Status: Ready — implementation not started
Depends on: Existing worker-conversation, task storage, and review contracts
Size: M
Context: [DeepSeek Harness assessment](../development/deepseek-harness-assessment.md)

## Outcome

Worker continuation, reviewer-requested changes, eligible model handoff, and a
post-commit follow-up retain the investigation and latest user corrections.
Changing execution stage must not silently restart the conversation.

## Implementation

1. Read `worker_conversation.py`, `engine.py`, `branch_controller.py`,
   `branch_operator.py`, `branch_worker_recovery.py`, `storage.py`, and current
   context-budget code. Reconcile the existing uncommitted engine/review changes
   with their owner before editing those files. Inventory every write that clears
   or replaces `task['messages']`; record whether it starts genuinely new work,
   switches roles/items, changes workspace generation, or resumes the same work.
2. Introduce one explicit continuation path using the existing saved exchanges.
   Start with `BranchController.continue_item()` and its REQUEST_CHANGES return.
   Append the current finding and current-state differences once. Avoid another
   full snapshot on every step; keep `refresh()` compatibility for old histories.
3. Preserve prior work after a source commit as historical context. Start a new
   evidence scope for the new patch; never reuse a prior approval as authorization
   for a later edit. Item/role transitions need explicit identity and relevant
   handoff context, not a mixed worker/reviewer message array.
4. Keep completed assistant/tool pairs in order. Interrupted or malformed calls
   remain diagnostics and cannot be re-executed because history was restored.
   Persist an explicit uncertain outcome if a crash prevents knowing whether a
   side effect completed. Inspect/reconcile that action before retrying it.
5. Extend existing content-free conversation receipts with transition reason and
   retained range/count where useful. Raw conversation remains local. Avoid a
   database migration or event-framework rewrite for this increment.
6. Document which previous snapshot/reset paths were replaced and remove their
   redundant continuation logic. Existing saved tasks may use a compatibility
   adapter; new requests must not update competing conversation representations.

## Acceptance

- A synthetic transcript with a user correction, discovered file location, edit,
  check, and review rejection preserves all those facts on worker continuation.
- A restart and an authorized model change preserve the same unfinished work;
  neither repeats a completed side effect nor duplicates user admission.
- A post-commit follow-up can refer to the prior change without starting discovery
  from the original prompt alone. Old check/review identities remain historical.
- Changed candidate IDs are never substituted into historical evidence to make
  it appear current. An old reviewer statement can inform a new review but cannot
  approve the new candidate.
- Existing unknown-history repair and accounting behavior remain explicit.

## Validation and handoff

Run `python3 -B scripts/check.py --plan --files <actual changed paths>` and the
relevant selected checks. Extend existing conversation/recovery tests with small
in-memory transcripts or mocks. Do not add a full multi-item Git workflow.
Record new-case runtime and the precise transitions covered. Mark Done only after
implementation and focused evidence; commit only this card's changes.
