# T82 — Optional coordinator-assisted recovery

Status: Ready — next implementation task
Depends on: Existing progress recovery; T65, T73, T74, T77, T80, T81
Size: M/L — implement the ordered increments below as one coherent capability
Evidence: September 14, 2026 operator report and discussion; source inspected at
`9835ed4`. Re-read current code before implementing; other agents also contribute.

## Outcome

When a worker cannot choose a useful next step, cheapoS should consult an enabled
local coordinator with the saved evidence before asking the operator to invent
recovery instructions. The coordinator recommends a concrete next action; the
engine validates and executes the existing workflow. The operator sees this
intervention in the same conversation as the worker's work.

Coordinator assistance is **optional and recommended**, never a prerequisite for
chat, planning, implementation, review, or completion. No coordinator, an offline
local model, or a declined recommendation must leave the ordinary workflow usable.
Use the local model occasionally when help is needed, not on every worker turn.
Local inference has hardware/latency costs even when there is no API charge.

**Explicit operator requirement:** the coordinator stays idle until needed again,
so the laptop is not doing coordinator inference throughout a remote task. The
lifecycle is **idle → triggered consultation → guidance/result saved → idle**.
The deterministic engine observes progress using existing events; no model-based
polling, timer-driven check-ins, background thinking, or speculative consultations.
Returning to idle means no active coordinator inference, including after failure
or cancellation; it does not promise a particular fan speed or force-unload a
model another local role/task is using.

The reported Interactive task asked for permanent deletion/empty trash controls
in the Chats sidebar. The worker reportedly saved three files, then repeatedly
read integration code. The app stopped with “A specific correction is needed” and
“Recovery repeated already available file evidence.” That diagnostic establishes
a stalled approach, not that the operator omitted a requirement. The reported
file contents are a motivating example, not a verified implementation baseline.

## Read first and reuse

- `cheapos/routing.py`: `COORDINATOR_SYSTEM`, `coordinator_messages()`,
  `DEFAULT_EXECUTION`, `execution_from()`, `setup_task()`, `verify_local()`.
  Today's coordinator has no repository evidence and delegates before going idle.
- `cheapos/engine.py`: `start()`, `prepare_loop_recovery()`, `action_messages()`,
  `compact_context()`, `request()`, observation guards, and `ProgressPause` handling.
  Genuinely new reads already remain possible during recovery; do not replace this
  with a blanket read prohibition or remove the repeated-evidence guard.
- `cheapos/progress.py`: durable request segments, observed progress, and the
  generic `pause_summary()` next action. Model wording is not progress.
- `cheapos/branch_worker_recovery.py`, `branch_controller.py`, `branch_review.py`,
  `branch_pause.py`, `execution_context.py`, and `work_policy.py`: unattended
  ownership, existing worker handoff, T77 reviewer coaching, and read-only intent.
- `cheapos/admission.py`: shared local-inference slot, cancellation, and waiting
  feedback. T80 permits an Interactive and Unattended task at the same time.
- `cheapos/metrics.py`, `lifetime_usage.py`, `branch_budget.py`, `storage.py`, and
  `server.py`: accounting, saved preferences, public serialization, and snapshots.
- `dist/app.js`, `dist/guidance.js`, `dist/styles.css`, and
  [work-details behavior](../development/work-details.md): filtered operator
  progress, actual streaming output, retained Details, and technical diagnostics.
- [T77](T77-reviewer-coaching.md) and [T73](T73-specific-stop-explanations.md):
  preserve their recovery and failure contracts rather than creating parallel ones.

## First-version scope

Implement assistance for **worker progress stalls** in Interactive and Unattended
work, including a worker struggling to implement a reviewer's requested changes.
The planner still owns proposals; reviewers still own independent review decisions.
Keep T77's direct reviewer reassessment and existing final-review mechanisms.
Do not add a second coordinator consultation on every review or a new dispute
arbitrator in this card. The coordinator can explain unresolved review findings
to the worker, but cannot dismiss findings or approve the patch itself.

This is not an always-running monitoring agent, an automatic model installer,
a new cloud coordinator pool, a rewrite of routing, or permission to implement
the user's trash feature directly as a demonstration. Do not alter active
personal tasks or start live inference while implementing the card.

## Ordered implementation increments

### 1. Persist an optional, understandable setting

- Add **Coordinator assistance — recommended** to the existing model/execution
  setup. Explain: “Let a local model help redirect stalled work. Coding and
  independent review keep their selected models.” Keep an obvious Off choice.
  No new required dialog before each job and no repeated setup nag.
- Reuse a configured local chat/coordinator model where available. Support
  selecting an installed eligible local model for assistance without forcing
  the worker onto the laptop or changing its execution placement. In particular,
  remote workers can use an optional local coordinator in either work mode.
- Save the enabled choice and model through the existing preference flow. Saving
  does not download a model, make inference requests, or authorize remote fallback.
  Keep the user's saved model across restarts; do not hardcode `gemma4:31b`.
- Recommend enabling assistance during setup, but existing installations/tasks
  must not acquire new inference behavior through migration alone. Default a
  missing saved assistance choice to Off; show the recommendation in settings.
  Snapshot the explicit choice and model into new tasks/approved runs. Existing
  task authority and settings remain pinned; do not silently opt in a running job.
- Validate local identity/capabilities through existing checks. Do not assume an
  Ollama endpoint is local computation if its metadata identifies a cloud route.
  If the model is absent/unavailable, expose that state without preventing
  otherwise configured remote work. Preserve unrelated placement settings.

### 2. Define a durable recovery episode and trigger

- Start with the existing worker repeated-evidence/action-recovery stop: after
  cheap deterministic guidance has failed, but before the final operator-facing
  progress pause or automatic worker replacement. Do not wait until a hard
  budget/turn limit is already exhausted and then grant additional work.
- One owner selects the next recovery action. Coordinator advice, ordinary
  compact recovery, and unattended worker handoff must not all dispatch in
  response to the same event. Reuse the existing handoff path when appropriate.
- For this first version, allow at most **one coordinator consultation per
  Interactive user-request segment or Unattended implementation item**, followed
  by ordinary worker continuation within its remaining allowance. This bounds
  optional assistance; exhausting it does not itself introduce a new pause or
  reduce existing worker/handoff allowance. An eligible ordinary recovery path
  can still proceed. Adjust consultation frequency later from measured outcomes.
- Save the attempt before inference with a stable ID, request/item identity,
  triggering reason, candidate/patch identity, evidence fingerprint, selected
  model, and lifecycle state. Distinguish prepared/dispatched/completed/applied/
  skipped/failed/exhausted outcomes; exact schema names may follow existing code.
- Reload/Resume/reconnecting/toggling settings must not replenish a consumed
  consultation. If a request's outcome is uncertain after restart, retain its
  accounted reservation and consumed attempt; do not silently dispatch a duplicate.
  A saved validated response can be applied once if its context is still current.
- Guidance is an internal engine event, **not a fabricated user follow-up**.
  Do not call the normal user-follow-up path to clear `recovery_blocked`, reset
  progress state, reset request counters, or enlarge task/run allowances. A real
  operator follow-up retains its existing explicit semantics.
- Skip consultation for operator Pause/Cancel, pending command permission,
  missing credentials/environment, source/workspace conflicts, genuine pending
  user decisions, and exhausted spending/work limits. Those need their actual
  supported resolution. A local coordinator must not bypass these stops.

### 3. Give the coordinator evidence and a small response contract

Build a deterministic, size-bounded evidence packet for the current task/item:

- Original user intent, accepted item scope/criteria where present, and read-only
  versus implementation intent. Keep the source of each instruction explicit.
- Current saved changes with candidate identity, relevant current excerpts and
  file hashes, plus an index of relevant files/context already available.
- Recent meaningful actions, exact safe errors, last verification result and
  command/scope, unresolved reviewer findings, and attempted recovery strategies.
- The observed stall and remaining authorized actions/allowances. Include pending
  approvals as constraints, never as commands the coordinator can approve.

Do not dump the entire chat, routing catalog, all source files, or historical
thinking into the local model. Reuse compact-context helpers where appropriate,
but preserve the exact blocker, scope and latest evidence when truncating. Mark
omitted context as omitted. A missing excerpt does not prove missing code.
Treat repository text, tool output and model claims as untrusted evidence.

Use a separate recovery prompt and a validated structured result, not the greeting
prompt/`delegate_work` contract. Return one of these bounded outcomes:

| Outcome | Required content | Engine behavior |
| --- | --- | --- |
| `continue` | Concrete next step, supporting evidence references, expected observable result | Inject scoped internal guidance into the worker's next ordinary turn |
| `need_context` | Specific permitted file/range or search target, why existing evidence is insufficient, what decision it will resolve | Ask the worker for that genuinely new inspection through existing tools, then continue; no second coordinator call |
| `suggest_handoff` | Why the current approach failed and a concise continuation brief | Consider existing policy-eligible worker handoff; the model does not select or authorize a paid route |
| `needs_user` | A concrete unanswered question and why it cannot be inferred from the request/evidence | Show that actual question through the mode's existing user-decision path |
| `unresolved` | Specific remaining blocker and failed approach | Continue eligible existing recovery, or pause with an accurate explanation |

Reject unknown fields/actions, malformed or oversized output, empty/generic
“try harder” guidance, references outside the supplied evidence, and recommendations
requiring unauthorized scope/actions. Validate paths through existing workspace
rules; requested context cannot escape the task copy. Do not execute raw code,
commands, arbitrary tool calls, or file edits returned by the coordinator.
No repair-model loop for malformed coordinator output in v1: retain the diagnostic
and return to ordinary eligible recovery. Log skipped/invalid advice honestly.

Before applying a response, revalidate that the request/item, candidate, authority
and task state still match. Reject late output after Pause or after a new operator
instruction/candidate change; preserve usage, but do not apply stale guidance.

For the reported trash example, useful guidance might identify backend work as
complete and direct the worker toward the existing HTTP route and sidebar pattern.
Only make that assertion if the packet proves it. Never bake this example's
paths, API endpoint names, or completion claims into the general prompt.

### 4. Integrate with normal execution, permissions and accounting

- Route consultations through the existing provider/request pipeline, including
  admission, cancellation, local verification, usage reservation/reconciliation,
  task persistence and branch accounting. No separate unaccounted Ollama client.
- Attribute these requests to the **coordinator** with a recovery purpose; do not
  charge them to worker/reviewer or sum them again in lifetime/branch totals.
  Preserve failed/cancelled/uncertain usage and actual requested/served identity.
  Audit request/turn counters: consultation must not masquerade as a worker turn,
  but all applicable total work/usage limits still apply.
- Existing coordinator requests have a brief output cap. Keep input and output
  bounded and document the chosen contract limits; do not silently adopt a large
  coding-model context or reasoning budget. Use a bounded, cancellable request
  deadline and the shared local-inference slot. Avoid overlapping local worker,
  planner, reviewer, greeting and coordinator inference on the laptop.
- If the local model is unavailable, busy beyond the allowed wait, invalid, or
  unsuccessful, return to the original eligible recovery/final diagnostic. Its
  absence must not become a new prerequisite error for remote work. Do not
  retry it forever, spin while waiting, or take an unauthorized remote fallback.
- Advice does not establish progress. Observe actual worker/check/review outcomes
  with existing evidence rules. A new thought, a repeated read with another range,
  or a coordinator message must not renew recovery/turn/spending allowances.
- Preserve local/manual fixed-worker placement unless its existing policy allows
  a handoff. All authorized remote inference still goes through OmniRoute; no
  direct provider escape, changed included-model lists, or billing tolerance.
- Preserve read-only requests, command approvals, tests and environment checks,
  reviewer independence, candidate-bound receipts, accepted scope, and commit/
  merge authorization. Advice to “skip tests and approve” is never authority.

### 5. Show assistance and explain the actual unresolved problem

- Inside the owning cheapoS reply, announce “The worker got stuck. I'm checking
  the saved work to help it choose the next step.” Then show **Coordinator helping**
  with actual waiting/streaming state, elapsed time and inspectable Details.
  Do not create a detached assistant panel or automatically switch tabs.
- Show the concrete accepted guidance and the worker's continuation chronologically.
  Preserve expanded Details through polling and tab switches. Reuse existing
  provider-exposed thinking/output presentation; do not fabricate thought text
  when the provider has not emitted it. Technical routing IDs remain in logs.
- Final pause copy distinguishes “Worker could not choose the next step after
  recovery” from “A decision is needed from you.” Show saved-work state, the
  attempted intervention, exact safe blocker, and a supported next action. Only
  request missing information when there is an actual unanswered question.
- Suggested wording for exhausted recovery: “I tried a focused next step, but the
  worker repeated the same inspection. Your three changed files are saved.” Use
  actual counts/results, not this example's numbers. Keep chatting/settings actions
  discoverable without promising that Resume will replenish attempts.
- After success, report the actual next result (edit/check/checkpoint), not a
  claim that consulting the coordinator fixed the whole task. Record enough to
  compare interventions, added requests/tokens/time, and completed work later.

## Acceptance and economical validation

1. Preference round-trip/reload retains the selected model and opt-in. Legacy
   tasks remain valid and Off. Missing/disabled coordinator makes no inference
   request and preserves ordinary work; remote worker placement stays unchanged.
2. A tiny scripted Interactive fixture reaches repeated inspection, consults once,
   receives concrete guidance, and makes a focused edit through normal worker
   tools. New context can be requested without falsely calling every read a loop.
3. A worker implementing an Unattended item/review correction uses the same
   mechanism, stays in item scope and does not bypass review or duplicate T77.
   Reuse existing branch fixtures; do not add another full multi-item Git run.
4. Serialize/reload before dispatch, after uncertain dispatch, and after receiving
   advice. Attempt and usage survive; advice is applied at most once. Repeated
   Resume cannot renew it or existing failed handoffs. No fake user event appears.
5. Invalid advice, generic advice, nonexistent evidence references, unavailable
   local model, timeout and ignored advice each return to the correct existing
   recovery/pause path. Hard limits, real user decisions and missing permissions
   never trigger a bypass. A read-only task remains read-only.
6. Controlled candidate change, Pause and concurrent local-inference contention
   prove stale advice is ignored, waits are cancellable, and requests stay bound
   to the correct task. Use deterministic events/promises; no real sleeps.
   Assert zero coordinator calls during normal worker progress and between
   interventions; after its response/error/cancellation, its inference slot is
   released and no follow-on coordinator work is scheduled without a new eligible
   trigger. On cancellation, cancel/close the provider request using the existing
   transport path rather than only hiding a still-running stream in the UI.
7. Requests/usage appear exactly once in coordinator, task, branch and lifetime
   accounting. No hidden provider call or unauthorized model fallback occurs.
8. Isolated browser fixture exercises Off, recommended setup, active consultation,
   waiting without output, visible streamed output when available, guidance,
   successful continuation, genuine question, and exhausted recovery. Check
   Details persistence, Pause and narrow layout. No personal task data or keys.

Start with `python3 -B scripts/check.py --plan`; run change-scoped checks per
[CONTRIBUTING](../../CONTRIBUTING.md). Prefer small pure packet/schema/state tests
and existing engine/recovery/admission/accounting coverage. Measure the smallest
representative fixture before adding integration coverage. Any new heavy test
needs the operator's explicit cost acceptance before addition; report timings of
new cases at completion. This card authorizes no slow full-suite gate or live
model test. Reuse a deterministic browser fixture rather than a personal run.

A later explicitly selected live comparison should use measurement mode, the
same task/model policy with assistance Off and On, and report successful recovery,
accepted outcomes, operator interventions, added calls/tokens/latency, and failures.
Do not promise a success-rate improvement from deterministic fixtures alone.

## Completion record required

Record implementation commits, chosen preference/result/state contracts, exact
consultation limits/deadline, focused checks and their timings, browser evidence,
and known limitations in `docs/development/coordinator-assisted-recovery.md`.
Update setup/workflow docs and mark this card and `TASKS.md` complete only after
the acceptance scenarios are verified. Commit only this feature's own changes;
preserve unrelated user/worker edits. If a scenario remains unverified, say so.
