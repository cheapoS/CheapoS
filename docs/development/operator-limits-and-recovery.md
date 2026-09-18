# Operator-owned limits and automatic recovery

Status: **Implemented baseline**, September 18, 2026.

The design contract below is implemented by T95–T100. See the
[user guide](limits-and-recovery-user-guide.md) and
[validation report](operator-limits-validation.md) for shipped behavior and coverage.

Extend the existing [scoped settings design](../design/settings-system.md) and
[autonomous completion contract](../../AUTONOMOUS_WORKFLOW.md). This design
replaces hidden cumulative work ceilings with explicit operator policy. It does
not remove usage accounting, spending authority, command permissions, workspace
boundaries or independent review.

Implementation tracking: [T94 — Operator-controlled limits and autonomous
completion](../tasks/T94-operator-limits-and-autonomous-completion.md) links the
six audit implementation cards, their order, boundaries and acceptance checks.

## Product contract

A new installation should let authorized work continue without a default
cumulative turn, request, review or time cap. Operators can select the limits they
want. Existing saved limits remain intact; upgrading must not silently make an
old bounded task unlimited or increase its spending authority.

An internal threshold means “choose the next useful strategy.” It does not mean
“give the operator an error.” Known provider failures, malformed output and
repeated ineffective edits should lead to payload repair, another tool, an
eligible alternate route, optional coordinator advice, or an availability wait.
A genuine missing permission, essential requirement or exhausted user budget
still requires the appropriate operator decision.

**No cap** means no operator work ceiling. It does not mean unlimited model
context, RAM, response size, spending, permissions, or retrying an identical
failure forever. **Automatic** means the engine chooses a per-operation value
from capacity and observed behavior; it is different from **No cap**.

## One dedicated section

Add **Limits & recovery** to the existing scoped settings UI. Do not add another
settings store or a second budget dialog with different semantics. Composer and
paused-budget links open this section for the captured chat ID.

At the top show exactly one destination:

- **This chat** — saved policy for this task, with current usage.
- **This project · future chats** — project overrides and inherited values.
- **Defaults · new chats** — installation defaults for future chats.

Each field shows its effective value and source, for example **No cap · from
project defaults** or **90 minutes · set for this chat**. “Use inherited value”
removes an override. Saving defaults never modifies another open chat. Display a
legacy value with unknown provenance honestly instead of inventing a source.

### Spending & access

Show free-only/authorized paid placement, spending cap and allowed connections,
with a link to existing role selection and permissions. A dollar amount is a
spending maximum, not permission to use an otherwise unauthorized paid model.
Keep explicit zero meaningful. Uncapped work must never enable paid fallback.

Do not preselect unlimited paid spending. Preserve the separate unexpected-charge
guard and usage reservations; changing a work budget does not bypass them.

### Work budgets

Offer **No work caps** and **Custom budgets**. In Custom budgets, each field is
independently **No cap** or a finite value:

| Field | Explain what it counts |
|---|---|
| Active working time | Execution time across planning, work, checks and review; show excluded human/resource waits separately. |
| Model requests | All role requests, including probes, retries and repairs. |
| Worker turns | Worker requests according to the authoritative role counter; do not confuse this with tool actions. |
| Tool actions | Controller-recorded tool attempts; make failed attempts visible in the breakdown. |
| Review tokens | Reviewer usage, including unresolved reservations, under the same accounting rules as other roles. |
| Checkpoints / iterations | Name the actual controller counter and define its boundary before exposing a field. |

Avoid redundant controls in the default view. Put advanced budgets in one
expansion, with the total and remaining allowance next to each enabled field.
Use “No cap,” not a giant numeric sentinel or JSON Infinity. Preserve safe numeric
validation without arbitrary application work ceilings such as 200 turns.

All enabled budgets apply consistently from the first planning request through
final review. A checkpoint inspection interval is not an iteration budget.
Internal handoffs do not reset usage, the active objective, or a user budget.

### Per-operation limits

Keep these distinct from cumulative work:

- **Response output: Automatic / explicit token cap.** Automatic uses verified
  route metadata, actual dispatch settings and observed truncation. Unknown
  capacity stays unknown; provider-default output is not unlimited output.
- **Verification deadline: Adaptive / explicit duration.** A timeout should
  select a useful authorized continuation. A quieter/different command still
  needs matching command authority, and passing assertions must not be removed.
- **Request deadline: Automatic / advanced override.** A dead connection cannot
  leave a task claiming that work is running indefinitely. Transport timeout
  changes route/strategy where authorized; it is not a cumulative work stop.

Explicit per-operation caps remain binding. If the next strategy would exceed
one, choose another authorized method or identify the required policy change.
Do not silently enlarge a user's cap in response to a failure.

### Recovery and capacity

Automatic recovery is normal product behavior, enabled by default. Reuse the
existing automatic versus pinned role contract. A future **Prefer this model**
choice requires tested fallback behavior in every role; **Only this model**
must remain an actual restriction.

The local coordinator is optional and consulted on eligible stalls. It remains
idle between consultations. Core provider and validation recovery must work
without a coordinator.

Show technical capacity in a read-only explanation: context window, response/body
size protections, provider cooldown, paging and retained evidence. Do not expose
every parser constant as a user dial. Reaching a representation limit should
normally page, stream, compact, or select a suitable authorized tool/model.

Suggested short explanation:

> Work budgets are optional. cheapoS keeps working within your spending, model
> and command permissions. If a model gets stuck, it changes approach
> automatically. Provider capacity still applies.

## State and authority

Extend `settings_store`, `settings_adapter`, `task_settings`, `measurement`, the
branch ledger and existing continuation policy. Resolve one effective policy
with value, unit, source, revision and enforcement behavior for each field.
Centralize comparisons; remove duplicate hardcoded checks in individual phases.

Represent missing/inherit separately from explicit no-cap, zero and Automatic.
A versioned schema can use `null` for no-cap work fields and a tagged Automatic
value for per-operation capacity. Keep currency and access rules in their
existing authority owners. Do not let `uncapped_work=True` bypass individually
selected finite budgets in a new schema.

Capture the effective policy before planning starts. Carry that snapshot into
the approved run and restore it on retry/restart. Planner output cannot add
Uncapped authority, and a changed global default cannot invalidate final review
of a different saved chat.

Changing an existing task uses the current revision and durable operation ID.
At a safe boundary, update only the selected policy, preserving counters, edits,
checks, findings, command grants and failed strategies. Reuse the existing
**Apply & continue** operation for paused work. For active work, retain the
current explicit pause/apply flow until queued safe-boundary changes are truly
implemented; do not advertise a seamless apply that the server cannot perform.

Finite budgets count cumulative usage. Raising a 100-request cap to 150 gives
50 more requests if 100 were already used. Resume never clears the counter.
Lowering a cap below current usage takes effect at the next safe boundary without
pretending it can undo an in-flight charge.

## Migration and documentation

Preserve every existing saved task policy. Preserve existing app/project limits
on upgrade, including legacy choices whose origin is unknown. New installations
can default to no cumulative work caps while retaining free-only spending
placement. Existing users can explicitly choose the new no-cap policy.

Translate legacy bounded/Uncapped settings into the new schema without resetting
accounting or changing model selection. Keep qualification measurement behavior
explicit during migration; it currently differs from ordinary Uncapped in check
and output handling. Remove legacy switches only after their authority and wire
semantics are represented and tested.

When implemented, add a short README section linking to user documentation:
where to change limits, which chats a setting affects, what No cap means, why a
provider can still impose capacity, and how an exhausted chosen budget resumes
from saved work. Until then, label this document as a design, not a feature.

## Ordered implementation and acceptance

1. **Resolve and capture policy.** Propagate Uncapped into the live planning
   draft as well as execution, and restore it on continuation. A tiny scripted
   planning allowance must not stop an explicitly uncapped proposal. Bounded
   work and money remain enforced. Two chats retain independent snapshots.
2. **Repair continuation gaps.** Normalize context/outage errors before general
   routing. Let context repair change the payload; let replacement-reviewer
   recovery continue through an unavailable candidate to an eligible independent
   reviewer. Preserve checks, failures and charges. These backend fixes should
   not wait for the settings UI.
3. **Unify policy enforcement.** Planner/worker/reviewer thresholds select new
   strategies under the saved policy. A malformed plan can recover and become
   approvable; a malformed edit can lead to a valid edit, check and independent
   approval without operator rescue. Never hide a valid reviewer finding.
4. **Expose the section.** Test scope/source labels, independently enabled caps,
   no-cap versus inherit, finite/zero validation, stale saves, and changing chat
   selection while a form is open. Preserve T91's migration and scope contract.
5. **Qualify budget and restart paths.** A selected budget stops at a safe
   boundary with a durable next action; increasing it continues that action.
   Provider outage waits or changes route without spending quality retries.
   Restart does not duplicate dispatch or lose an uncertain reservation.

Use small deterministic tests and fake clocks; reuse existing authorization,
review and persistence fixtures. No live providers, deliberate long sleeps or
new full multi-item Git workflows are needed for the initial slices. Disclose
and obtain acceptance before adding heavy tests under AGENTS.md. Report measured
new-test cost. Docs-only changes need link/whitespace checks, not runtime suites.
