# T28 — Durable branch-run plan and item states

**Depends on:** completed T01–T27. **Size:** M. **Result:** the controller can represent one bounded multi-item job without changing existing chats.

Read [BRANCH_RUNS.md](../archive/BRANCH_RUNS.md) and AGENTS.md first. This card builds state/validation/storage only; it does not execute a plan or create a branch.

## Read first

`cheapos/storage.py`, `Engine.create/start/event`, `Runtime`, `public_task` in `cheapos/server.py`, `cheapos/metrics.py`, and task metadata/restart tests. Check the distinction between live runtime objects, stored copies, and separate metadata.

## Implementation

1. Add a versioned optional `branch_run` record to an ordinary task, with pure helpers in a focused module such as `cheapos/branch_runs.py`. Old records without it keep manual behavior. Unknown/newer schema versions must not execute automatically; expose a recoverable compatibility message while keeping the saved record.
2. Store a run ID, schema version, plan revision/digest, project identity, selected base ref and immutable base SHA, integration target ref, exact feature ref, expected feature tip, workspace mapping, status, current item ID, and authorization reference. Add cumulative limits/consumption, timestamps, and references to pending operations and final evidence. Use stable IDs, not array positions or natural-language titles, for relationships.
3. Define item records: ID, title, instructions, dependencies, acceptance criteria, required check specifications, status, bounded recovery state, evidence references, outcome summary, and commit receipt. Support `pending`, `working`, `checking`, `reviewing`, `committing`, `committed`, `satisfied_without_change`, and `blocked`. Final revision items retain links to the original work.
4. Define run transitions such as `draft`, `awaiting_authorization`, `running`, `paused`, `blocked`, `finalizing`, `ready_for_merge`, `merging`, `merged`, and `left_on_branch`. Use typed pause reasons to distinguish waiting for a command grant, missing setup, exhausted work, and branch drift. Map these to existing task status/polling semantics; do not make metadata archive/trash flags execution states.
5. Validate plans server-side. Start with 1–50 items, titles up to 120 characters, instructions up to 4,000 characters/item, at most 12 criteria of 500 characters/item, and an aggregate 128,000-character text limit. Validate uniqueness, dependency references, acyclic ordering, nonempty criteria, and serializable finite limits. Reject oversized/invalid plans explicitly; never execute a truncated subset. Document any justified adjustment before dependent cards consume it.
6. Keep one controller-owned task record authoritative. Update run transitions under the existing engine/storage locking discipline and save atomically. Return bounded summaries through list/bootstrap and full permitted state through the task endpoint; omit command-grant secrets/tokens from ordinary summaries. UI title edits must not overwrite run progress, or vice versa.
7. Keep the original user request, captured plan revision, and item outcomes separate. Do not replace task history with the active item's prompt. Define deterministic event IDs/sequence numbers so a resumed transition can be displayed once.

## Acceptance and validation

- Round-trip a valid three-item plan and all supported states through storage/restart.
- Reject cycles, duplicate/missing IDs, invalid numbers/types, excessive input, and illegal completion transitions.
- A legacy task still loads, runs, and presents unchanged. An unknown schema is readable but cannot dispatch.
- Concurrent metadata changes and execution-state updates preserve both; list/full responses agree on progress.

Add focused tests, for example `tests/test_branch_runs.py`, and relevant HTTP/storage compatibility coverage. No model calls, Git mutations, UI, scheduler, or permission grant is needed for this card.

## Completion record

Status: Done

Behavior delivered: Versioned, strictly bounded plans; stable IDs and event sequences; evidence-gated transitions; controller-owned atomic updates; redacted list summaries; unknown-schema dispatch refusal and restart pause mapping. Original prompts and captured inputs remain separate from item state.

Acceptance evidence: Pure lifecycle/invalid-plan tests plus storage round-trip, concurrent metadata updates, list/full consistency, and manual-dispatch, rollback, steering, and limit-change guards.

Commands and results: `test_branch_runs.py` 10 PASS; `test_branch_state_storage.py` 5 PASS; `test_task_metadata.py` 5 PASS. Agent fast suite 50 PASS.

Browser scenarios and results: Not required for this backend-only card.

Remaining limitations: No execution/start UI in this card. Check specs are bounded to 12 entries / 4,000 characters each, captured inputs to 256,000 characters; accepted dependency order must already be topological. Later cards validate concrete command/authority/evidence contracts.
