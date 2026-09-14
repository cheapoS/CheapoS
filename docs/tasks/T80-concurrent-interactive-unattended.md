# T80 — Use Interactive chat while an Unattended job keeps working

Status: Complete
Depends on: T79; existing task workspaces, authorization, accounting, and Git receipts
Size: L — deliver the bounded case before expanding concurrency
Evidence: September 14, 2026 operator report; source inspected at `72532b4`.

## Outcome

An operator can start and use an Interactive task while an Unattended job runs.
Each conversation owns its progress, model requests, checks, permissions, budget,
pause/resume state, and saved files. This is concurrency between tasks; items
within one approved Unattended plan still execute in their supported order.

## Confirmed starting points

- `dist/app.js`: `renderComposer()`, `sendChat()`, and steering controls treat
  any other busy chat as a global blocker. `state.sending` also needs an ownership
  audit so a request in A cannot overwrite B's draft or controls after switching.
- `cheapos/engine.py`: `Engine.start()` rejects another live runtime. Other
  runtime-wide checks govern shutdown/setup and are not all execution locks.
- `cheapos/branch_controller.py`: planning, start, resume, and guidance/recovery
  paths contain checks over every runtime. `cheapos/branch_completion.py` also
  gates final operations. Inventory these by purpose before changing them.
- Shared gateway settings, provider probes/cooldowns, credentials, session
  permissions, process resources, and source Git repositories remain shared
  even when task workspaces are separate.

## Bounded implementation sequence

1. **Admission contract.** Add one server-owned admission decision used by
   Interactive start and branch planning/start/resume. First prove two independent
   tasks (one Interactive, one Unattended); make the concurrency allowance
   explicit. Return a specific resource/capacity blocker. Keep one live runtime
   per task. Do not simply delete every `runtimes.values()` check or promise
   unbounded parallelism. A durable queue is separate scope; never display
   “queued” unless work is actually scheduled and its cancellation is supported.
2. **Independent ownership.** Give each task its own immutable request/placement
   binding, counters, cancellation, pending command approvals, error state, and
   streams. Retain task budgets across retries/restarts. Pause A must not stop B
   or the shared gateway. Restart continues to save and pause tasks rather than
   starting both automatically. Existing project-session grants may be reused
   only where their original identity/scope contract permits.
3. **Resource coordination.** Keep critical sections short: never hold a global
   scheduler/engine lock across inference or checks. Audit shared caches and
   probe coalescing for concurrent access. Respect provider/account cooldowns
   across both tasks; show real waiting reasons without consuming futile retries.
   Local inference and check execution need explicit capacity policies too, so
   two tasks do not silently double the laptop's heavy workload. Resolve these
   settings before enabling the feature; concurrency is not spending permission.
4. **Repository isolation.** Use separate task copies/feature refs. Serialize
   integration operations against the same source checkout/ref, retain expected
   tip and cleanliness checks, and invalidate stale previews after another
   commit lands. Never auto-stash, overwrite another task's patch, or merge it
   under another task's approval. Different projects should not share a Git lock.
   Preserve current commit receipts, reconciliation, and final human approval.
5. **UI integration.** Drive each chat's controls from its own state plus server
   admission, not a blanket “any task busy” rule. Keep both running indicators
   visible in the sidebar and stream the selected conversation's work. Late
   responses must update their owning task, not the currently selected chat.
   An Unattended run must not steal focus when the operator chats in B.

## Acceptance and validation cost

- Hold A at a controlled provider barrier; B can read/respond in another isolated
  workspace before releasing A. Both finish under their own model/spending policy.
- Duplicate start requests produce one runtime per task. Exceeding configured
  capacity returns a clear saved/draft state with no hidden dispatch.
- Pausing, failing, retrying, or requesting approval in A does not alter B's
  files, draft, usage, role identity, or permission request. Include a late-response
  case after switching chats and a shared-provider quota case.
- Two tasks targeting one repository never integrate simultaneously; the second
  stale preview cannot merge without the existing fresh-review/reconciliation
  path. Independent projects are not blocked by that repository lock.
- Start with deterministic barriers/events and small unit/HTTP cases. Reuse
  existing Git integration fixtures for lock and stale-tip checks; do not add a
  pair of full multi-item runs as the default regression. Measure any uncertain
  fixture first and disclose heavy-test cost for operator approval before adding.
- Browser proof uses disposable data and scripted providers. No personal tasks,
  paid calls, or alteration of a live run. A later live qualification trial must
  use explicit measurement mode while preserving its authorized model/spend policy.

Completion: Implemented in `work/pending-tasks`; the closing implementation commit
contains this card. See [validation, browser evidence and measured test costs](../development/usage-and-concurrency-validation.md)
and [the work-mode guide](../unattended-runs.md). No live inference or application
restart was performed.
