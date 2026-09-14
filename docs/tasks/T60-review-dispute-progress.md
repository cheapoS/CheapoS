# T60 — Detect repeated review disputes and preserve counterevidence

Status: Done
Priority: High — convergence
Depends on: T53, T57, T58, T59
Size: M
Planning baseline: `5a463b4`, September 14, 2026

## Outcome

The same unresolved worker/reviewer dispute does not start over because feedback
was paraphrased or line numbers moved. cheapoS can show what changed, what remains
disputed, and when continuing the same repair is no longer producing evidence.
New real defects remain eligible for review; repetition never implies approval.

## Entry points and existing guards

Read [branch_disagreement.py](../../cheapos/branch_disagreement.py) (`attach`,
`unsupported`, `ensure_available`), [branch_review.py](../../cheapos/branch_review.py)
(observation fingerprints), [branch_final.py](../../cheapos/branch_final.py)
(correction attempts), [metrics.py](../../cheapos/metrics.py), and the repair
brief from T58. Reuse the pause contract from T53.

Existing guards catch identical defect payloads or repeated evidence. Their keys
include full text, so wording/location changes can create a fresh identity.
Five tasks eventually converging is not proof that other runs cannot cycle.

## Work

1. Persist a small dispute ledger per run/item using canonical original criterion
   references, affected behavior/location, and evidence provenance. Separate
   identity from display wording and volatile line numbers. Keep links to each
   reviewed candidate and repair attempt rather than resetting history on edits.
2. Prefer explicit references to an existing finding in repair/re-review packets.
   For a newly worded finding, use conservative structural matching to flag a
   possible repeat. Do not add another model call or embedding service to decide
   identity. Similar wording or the same function alone cannot establish that
   two genuinely different defects are the same.
3. Track requested, reproduced, corrected, independently resolved, disproved,
   and unresolved dispositions with their evidence references. Preserve worker
   counterevidence through compaction/restart and present it to the reviewer.
   A model's unsupported assertion cannot clear a defect or claim progress.
4. Define progress in terms of resolved findings or new relevant evidence, not
   any changed file/hash, another tool call, or a rewritten complaint. A moved
   line or unrelated edit alone must not renew an exhausted dispute allowance.
5. Reuse existing bounded disagreement/recovery allowances. Repeated unsupported
   requests must lead to a specific pause showing the dispute and counterevidence,
   or an already authorized alternative path. Do not add a paid arbiter, silently
   change reviewer, lower review standards, or raise limits to escape a loop.
   Resume/restart alone must not erase the relevant ledger or reset the allowance.
6. Keep genuinely new findings and regressions distinguishable. A potential-repeat
   match requests evidence comparison; it never suppresses a valid new rejection
   or automatically approves code because the models have argued long enough.
7. Emit compact structured events for actual review decisions, schema corrections,
   context reads, repair attempts, and dispute outcomes. Transport retry counts
   remain T50's responsibility. Use existing storage bounds and visible unknown/
   truncated-history markers rather than an unbounded log. T55 reconciles reports.

## Acceptance

- Paraphrased feedback and shifted line numbers for the same referenced defect
  retain history and counterevidence across repairs and restart.
- Two distinct defects in one criterion/function are not silently merged or
  suppressed. A regression after a valid fix can be reported as a new occurrence.
- Repeated unsupported disputes reach the existing bounded stop with a specific
  cause and supported next action, without clearing earlier work or approvals.
- Changed files alone do not count as dispute resolution. Confirmed new evidence
  remains visible, and no repetition threshold generates automatic approval.
- Events distinguish network retries, review requests, decisions, and repair
  cycles so review-count reporting has an explicit basis.

## Focused validation and handoff

Start with the selector plan. Use pure ledger/state transitions, synthetic
candidate IDs, and save/load dictionaries. Reuse existing disagreement/recovery
coverage; do not run dozens of worker turns or introduce real sleeps. Report
new-case timings and disclose any heavy addition before adding it. Record matching
limitations explicitly; do not claim universal semantic-loop detection. Commit
the implementation and update this card and TASKS.md.


## Completion record — September 14, 2026

Implementation: `e0fcc51` (with foundations `abe2545`, `226b604`, `3b48cef`).

A versioned bounded dispute ledger retains original criterion IDs, path, candidate attempts, allegations and worker counterevidence. Explicit finding references survive paraphrasing, shifted lines and appended repair items. Structural matches without a reference flag possible repeats; distinct expected/observed/reproduction signatures remain distinct. Only independent approval resolves a record; later regressions get a new occurrence. Changed file hashes, Resume and restart do not renew the existing three-attempt allowance. Exhaustion uses a typed review-dispute pause, not approval or paid escalation. Activity displays escaped allegations/counterevidence (up to eight unresolved records), and explicit request/context/correction/repair/decision events support future counts.

Validation: six small ledger/repair cases cover persistence, original-ID mapping, distinct claims, regressions, tampered pending criteria, localized diffs and optional advice. Combined final deterministic selection: 27 tests in 0.011s. The added Activity markup test passes in about 1ms; existing Node cases remain passed. Browser rendering remains pending. Matching is deliberately conservative and does not claim universal semantic-loop detection.
