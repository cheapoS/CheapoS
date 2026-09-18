# T99 — Build Limits & recovery settings and effective request budgets

Status: **Implemented — integration validation pending**, September 18, 2026. Priority: **P2**.
Parent: [T94](T94-operator-limits-and-autonomous-completion.md).
Canonical contract: [Operator-owned limits design](../development/operator-limits-and-recovery.md).
Build on T91 and integrate T95–T98; backend reliability fixes must not wait for
this UI. T94 tracks the overall outcome; this card owns schema, controls and
request-budget implementation rather than duplicating the other cards.

## Problem and evidence

Users cannot distinguish chosen work budgets, fixed recovery counters and
provider capacity. At baseline `49cbecb`, ordinary Uncapped still sends the
configured output allowance (default 2,048; validator maximum 16,384). Zero-rate
measurement omits `max_tokens`, meaning provider default. Reservations/context
headroom still use the configured value. Catalog output capacity is read but
not used for the dispatched allowance.

The adapter's 16,384-token reasoning floor is latent: normal provider validation
drops the relevant flag. Do not claim it caused historical incidents. Resolve
actual wire behavior and provenance rather than inferring it from names/settings.

## Ordered slices

1. **Effective policy and migration.** Extend the existing versioned settings
   store. Separate missing/inherit, explicit no-cap, finite zero where meaningful,
   and Automatic. Preserve saved app/project/chat policies, pins, usage and
   unknown legacy provenance. Fresh installations default to no cumulative work
   caps with free-only placement; upgrades do not silently uncap old tasks.
2. **One request budget resolver.** Derive effective response output, context
   reserve, reservation basis and actual wire fields together. Use validated
   route capacity, observed truncation and remaining monetary authority. Show
   unknown/stale metadata honestly. Explicit output caps stay binding; automatic
   adjustment cannot authorize a paid route or exceed approved spending.
3. **Scoped UI.** Add Limits & recovery to This chat, This project · future chats,
   and Defaults · new chats. Show source/effective values. Offer independent
   optional work budgets, advanced per-operation controls, recovery policy and
   read-only capacity explanations. Reuse existing save/revision/idempotency flows.
4. **Apply and continue.** A paused task can apply the explicit change and continue
   its unfinished phase without resetting usage. Preserve the current active
   pause-to-apply boundary until seamless safe-boundary updates actually exist.
5. **Documentation.** Add README/user guidance only for shipped controls: scopes,
   No cap versus Automatic, budget exhaustion, provider capacity, reservations
   and automatic recovery. Keep accounting breakdowns in Details.

Do not expose every parser constant as a settings field. Keep technical memory
protection, independent review, command grants and exact-evidence checks. Raising
100 requests to 150 after 100 were used grants 50 more, not a fresh 150. A new
schema must not let legacy `uncapped_work=True` override selected finite fields.
Measurement's distinct wire/check semantics require explicit migration coverage.

## Implementation starting points

`cheapos/settings_store.py`, `settings_adapter.py`, `task_settings.py`,
`measurement.py`, `engine.py` limits/dispatch, `branch_controller.py`,
`branch_budget.py`, `providers.py` reservation/adapter, `context_budget.py`,
`gateways.py`; `dist/settings.js`, `dist/app.js` limit/composer flows.

Extend `tests/test_settings_store.py`, `tests/test_task_settings.py`,
`tests/test_uncapped_work.py`, `tests/test_measurement.py`,
`tests/test_context_budget.py` and the existing scoped-settings frontend tests.

## Acceptance

- [ ] Two saved chats remain isolated when project/global defaults change.
  A form stays bound to its captured chat even if navigation changes selection.
- [ ] No cap, inherit, explicit zero, finite values and Automatic round-trip
  through UI/API/storage. Unsafe numbers and stale revisions reject atomically.
- [ ] Existing bounded/Uncapped choices migrate without authority expansion or
  counter resets. New default policy applies only where intended.
- [ ] Planning through final review use one effective policy. Exhausted selected
  budgets name the actual field/source and retain the next continuation.
- [ ] Effective output/wire/reservation metadata agree for known, unknown and
  stale route capacities, reasoning-heavy output and low remaining paid budget.
- [ ] A truncated response produces a materially different authorized output
  strategy or capacity adjustment; partial tools never execute.
- [ ] Changing only a budget resumes the pending review/check/work operation,
  retaining valid receipts and cumulative consumption.
- [ ] Browser checks cover narrow layout, source labels, disabled fields, errors
  and correct save destination. README reflects actual implemented behavior.

Follow T94's focused validation and test-cost rules. Use fake capacities and
providers; no live billing/measurement calls or full suite needed by default.

Independent nullable work fields extend the existing settings owner. Legacy
policies remain unchanged; fresh installs use no work caps and free-only routes.
The request budget resolver aligns context/output/reservation; explicit caps
remain binding. Scoped settings and accounting tests: 28 passed in 0.034s;
measurement output compatibility passed separately. Browser validation pending.
