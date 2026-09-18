# T100 — Keep large evidence and long-running tasks usable

Status: **Completed**, September 18, 2026. Priority: **P2**.
Parent: [T94](T94-operator-limits-and-autonomous-completion.md).
Deliver the three slices below separately. Use T97's error categories and T98's
continuation contract; align per-operation controls with T99. Storage measurement
can start independently, without changing running tasks.

## Problem and evidence

At baseline `49cbecb`:

- Verification output over 2 MB terminates the process in every mode, including
  measurement. This infrastructure pause can bypass normal worker handoff.
- Final review rejects a manifest over 1M characters despite chunking; individual
  packets are capped at 60,000. A size ceiling can block already implemented work.
- Task saves serialize, fsync and deep-copy the full record; publishing deep-copies
  it again. Retained histories can grow substantially. This is a confirmed growth
  mechanism, not a measured diagnosis of a particular UI freeze.

## Slice A — Verification output without task failure

Separate process execution from bounded display/prompt capture. Stream output
into durable evidence with bounded previews and paged retrieval rather than
killing a legitimate check solely because the preview buffer filled. Define disk
quota, cleanup, truncation markers, cancellation and unavailable-storage behavior.
Do not replace one memory limit with unbounded RAM or disk use.

If a resource constraint still requires another verification strategy, select a
permitted quieter command or other authorized continuation. Retain exact command,
exit status, candidate/environment identity and an explicit record of any output
loss. A missing/truncated log is not a passing check. Never weaken assertions or
silently execute an unapproved command.

Acceptance: a synthetic stream crosses the old threshold, the check completes,
and the relevant tail/failure evidence is retrievable; cancellation, storage
failure, explicit deadlines and stale-grant rejection remain correct. Preserve
uncertain outcomes. Reuse current candidate-bound passing checks.

## Slice B — Complete paged final-review evidence

Replace the whole-manifest character stop with stable indexed evidence pages.
Keep bounded request packets, complete ordered coverage, candidate-bound receipts,
criteria synthesis and reviewer independence. Avoid resending identical large
context for every page. Expose accurate chunk/coverage progress from the actual
manifest, including resumed or invalidated pages.

Acceptance: synthetic evidence larger than the previous aggregate limit reaches
an independent final decision without operator intervention. Prove every required
segment/criterion is covered exactly as intended; partial coverage never approves.
A changed candidate invalidates affected evidence, and restart reuses only valid
coverage. An invalid reviewer response uses automatic recovery with the same
manifest instead of restarting the entire review.

## Slice C — Measure and reduce history overhead

Measure serialization, save/fsync, publish and changed/unchanged polling on small
synthetic records and a representative generated long history. Record wall time,
bytes copied/written and growth; do not use personal chats as test fixtures or
claim a performance regression from file size alone.

Use the evidence to choose compact live state plus paged/journaled history if
needed. Preserve crash consistency, schema migration, event order, full evidence
references, cumulative counters, usage reservations and saved continuations.
Keep polling responsive without dropping active status or falsely reporting work.

Acceptance: publish/save/poll work avoids repeatedly copying full history where
the measured design warrants it; restart reconstructs equivalent durable state.
Report comparable before/after measurements and remaining tradeoffs. Do not add
an arbitrary maximum history size that stops an otherwise useful task.

## Implementation starting points

- Checks: `cheapos/workspace.py`, `cheapos/check_output.py`, engine check-error
  handling and `tests/test_check_output.py` plus focused workspace fixtures.
- Review: `cheapos/review_context.py`, final-review callers/recovery and
  `tests/test_review_context.py`, `tests/test_branch_final_recovery.py`.
- Persistence: `cheapos/storage.py`, task publication/poll handlers, metrics and
  `tests/test_branch_state_storage.py`. Verify current owners before changing them.
- Context: [long-task refresh](../development/long-task-refresh.md) and
  [test performance policy](../development/test-performance.md).

## Validation and boundaries

Keep each slice independently reviewable and record its status here:

- [x] A — bounded verification capture with useful continuation.
- [x] B — complete final-review paging beyond the old aggregate ceiling.
- [x] C — measured history/storage improvement with durable migration.

Use in-memory streams, small fixtures and fake interruptions first. A test need
not generate an entire agent/Git project to prove page coverage. Measure the
smallest representative storage benchmark before proposing a larger one. Disclose
runtime, frequency and why cheaper coverage is insufficient before adding heavy
regression tests under AGENTS.md. Follow T94's scoped validation and commit rules.

## Slice measurements

A: checks retain up to 64 MB per run / latest eight runs (512 MB per task),
with bounded preview and paged reads. The existing noisy-process test now exceeds
2 MB, finishes successfully and verifies its tail; its previous ten-second sleep
was removed. Cancellation and engine publishing remain covered. Nine output/poll
checks passed in 1.979 seconds. Storage failures fail the check rather than
manufacturing passing evidence; spool files are removed with the temporary dir.

B: ordered pages remove the 1M aggregate barrier. Large packets are reviewed by
page before synthesis, with the complete original retained by reference. A pure
synthetic >1M-character case verifies exact reassembly and rejection propagation.

C: generated histories only; ten / 2,000 events with 4 KB content each. At 2,000
events (8,249,006 serialized bytes), before/after wall times in milliseconds:
serialization 7.888 / 7.653; save+fsync+snapshot 23.360 / 22.244;
publish 2.023 / 0.009; changed poll 2.074 / 2.000; unchanged poll 0.081 / 0.044.
Live publish copies only five volatile fields, not history. Save still writes a
complete atomic snapshot, with compact JSON. Changed polls still copy the full
snapshot; unchanged polls remain history-independent. These measurements do not
justify a new history-journal migration yet. Durable schema and restart behavior
remain compatible. Single-run measurements are indicative, not latency guarantees.

Validation: [T94–T100 completion report](../development/operator-limits-validation.md).
