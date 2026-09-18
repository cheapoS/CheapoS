# T94–T100 completion and validation

Completed September 18, 2026. No live model calls or production task mutations were used for qualification.

## Delivered

- **T95:** planning captures trusted operator policy before dispatch and restores the saved allowance on Resume. Model proposals cannot widen it; explicit operator amendments can.
- **T96:** explicit context errors repair the request projection with retrievable original evidence and intact instructions/tool pairs. Irreducible requests can select a known larger authorized route; pins and unknown capacity remain meaningful.
- **T97:** provider and proxy failures share classification across request paths. Replacement-reviewer outages move to another eligible reviewer or a scheduled wait. Saved selection/dispatch state and uncertain usage survive recovery.
- **T98:** planner and worker recovery preserve strategy episodes, conversations, attempts and next actions. Former repair/discovery/handoff counters no longer act as arbitrary completion ceilings. A real missing prerequisite still pauses with a specific reason.
- **T99:** independent nullable work budgets and per-operation controls appear in scoped Limits & recovery settings. Legacy policies remain captured; fresh installs have no cumulative work caps. Context, reservation and wire output use the same effective budget. Budget amendments resume saved work without resetting usage or review evidence.
- **T100:** bounded disk-backed verification output, complete paged final review with reusable page receipts, and measured lower-cost history publication. Existing durable snapshots remain compatible; no speculative journal migration was needed.

T101 remains a separate follow-up and is not marked complete by this work.

## Deterministic qualification

The final focused selection passed **283 tests in 8.677 seconds** across 34 relevant modules. Follow-up focused tests for irreducible context routing, planning amendments and reservation diagnostics also passed. Existing measurement coverage passed separately: seven tests in 22.131 seconds, dominated by its existing three-item workflow (21.955 seconds); it was not repeatedly rerun.

Coverage includes HTTP context classification through retry for planner/worker/reviewer, third malformed worker response through valid edit/check/independent approval, continuation beyond the former handoff ceiling, first replacement-reviewer outage, explicit bounded stop followed by allowance increase, saved planning limits, uncertain accounting, pins, cooldown waits, check reuse, final-review restart/page reuse and storage compatibility.

Browser validation at 390px checked no horizontal overflow, source and usage labels, disabled fields, explicit zero/no-cap values, retained error drafts/idempotency, and saving to the captured chat after selection changes. Scoped settings JavaScript checks passed. No full Python suite was required.

New pure/in-memory regression cases run below 0.1 seconds per case in the focused runs. Existing workflow fixtures were reused rather than adding a new heavy multi-item workflow; the malformed-output completion fixture took about 1.0 second. The existing noisy-output test now writes 2.1 MB and verifies retained tail evidence without its former ten-second sleep.

## Storage measurement and boundaries

For a synthetic 2,000-event, 8,249,006-byte history, publication fell from 2.023 ms to 0.009 ms by copying only volatile fields. Snapshot save including fsync was 23.360 ms before and 22.244 ms after; full durable snapshots remain the dominant cost. Changed polls were about 2 ms. These local measurements justify the bounded publication improvement, not a claim that persistence is constant-time.

Verification retains up to 64 MB per run and eight runs per task, with bounded head/tail previews and paged access. Quota/storage errors do not become passing checks. Large final packets are reviewed in complete pages; approval requires all pages and final synthesis. Capacity metadata can be stale or unknown, so Automatic uses an honest conservative fallback rather than promising unlimited provider capacity.

The [user guide](limits-and-recovery-user-guide.md) describes scopes, migration, counters and recovery behavior. Live provider reliability remains environment-dependent and was not inferred from deterministic tests.
