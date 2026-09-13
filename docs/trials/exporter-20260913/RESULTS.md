# Exporter live qualification — September 13, 2026

## Attempt 1: incomplete

App/source `0c3375954042d3a1ff71587612bbed4d655c3b9f`, task
`4c8ac1a25ab44f45a005a9dd79c6890e`. Worker Kiro Sonnet 4.5; reviewer
Kiro Haiku 4.5 was configured but never reached. Operator-authorized included
access, measurement mode, no paid/local fallback. Included marginal estimates
are not invoices. [Machine record](attempt-1.json).

Planning took one request (10,508 accounted tokens). The three requested items
and exact commands were generated; the observer reordered the identical final
check list through the proposal-edit API. Planning is therefore labeled assisted.
The original and corrected proposals remain private alongside the task state.

Execution took 295.90 seconds wall time, 50 requests and 1,286,731 accounted
worker tokens, including an uncertain reservation for the final streaming error.
No reviewer requests, completed commit receipts, or execution interventions.
Provider-reported output tokens were zero; that is not proof of zero generated
output. Source main and both source/candidate acceptance files stayed unchanged.
No merge or push occurred. The candidate contains the worker-written formatter
and tests only; endpoint/UI/docs and independent qualification are incomplete.

The worker's 36 formatter tests passed in 0.002 seconds (0.18 seconds observed
command wall time). The independent seven-test command failed in 0.003 seconds
(0.18 seconds wall time). Its failure was an overstrict layout assertion: a
Checks heading with Total: 2 on the next line is valid. Subsequent observer review
also found a fixture error: changed-patch commit receipts carry outcome `ready`,
not the fixture's `committed`. The worker copied that incorrect assumption.
The v1 pack cannot establish correct real receipt reporting even if it passes.
Its frozen digest was
`ce21e1075fc06d9f7810ca6a41d5f133cfcb4c6acc38a92de5385169fa473397`.

Repeated reads consumed much of this attempt. Context compaction reset the
repeat counter; [the separate controller repair](../T44-compaction-read-loop-repair.md)
preserves observations through compaction. This attempt used the original runtime
throughout and is not retroactively labeled repaired or successful.

Browser qualification is pending: there is no complete exporter endpoint/UI to
exercise. No screenshot or mocked download is claimed as acceptance. T44 stays
Blocked for this candidate; T45's failure observation is complete. Next correction:
freeze a corrected independent pack and repaired runtime before a fresh attempt.
The observer has written none of the exporter implementation.

## Attempt 2: incomplete, loop safeguard observed

App/source `d1bc3a36c622d3860358214e3508c5d4961d8945`, task
`9362b4ce0c1740679d5f0a5cfc581748`. Same included pair; fresh bounded probes
passed before planning. Runtime and acceptance v2 were frozen in a separate
worktree. V2 digest:
`58630b139a9c8a69402bd4eda5f67f312ff924e7136b818f57befb36ec2844b0`.
[Machine record](attempt-2.json).

Planning took one request and 10,922 accounted tokens. The planner produced 13
criteria; the observer combined two related clauses without removing either so
the original scope fits the controller's 12-criterion final-repair format. This
is planning assistance, not autonomous planning success.

Execution took 185.70 seconds wall time, 26 requests and 665,226 accounted worker
tokens. There were no execution interventions, reviewer calls, completed feature
commits, merge or push. The run paused with `progress_limit` after repeated
unchanged file evidence in recovery. The repaired guard preserved its observations.
This is evidence of that safeguard, not evidence that the feature was delivered
or a controlled speed comparison: the pack and generated plan also changed.

The worker wrote a formatter and tests. Its only in-run check occurred before
the test file existed and correctly failed on zero discovered tests. After the
pause, the observer ran the two relevant formatter commands, without editing the
candidate: worker tests had 40 passes/1 failure in 0.001 seconds; independent v2
had 2 passes/5 failures in 0.003 seconds. The worker-test failure expected a raw
underscore despite Markdown escaping. Some v2 assertions similarly failed valid
escaped category text; these test defects are retained and corrected separately
for future qualification. The candidate also has real deficiencies: missing
accounting/check sections disappear, invalid integration receipts can report
merged, and no-change items can display a commit abbreviation. The required full
confirmed SHA is shortened. No passing feature claim is justified.

Endpoint, UI, documentation, completed receipts and real browser downloads remain
missing. Source main and frozen source/candidate acceptance packs are unchanged.
T44 is Blocked; T45's incomplete-outcome report is Done. No unchanged Resume or
observer-written exporter is substituted for a completed live task. Next feature
attempt should address worker retention of the current step through compaction
and qualification fidelity, then use a newly inspected plan. T46–T48 proceed from
these recorded findings in their separate development branch.

## Readiness accounting

Readiness probes are separate from planning and execution. The original synthetic
no-argument probe was inconclusive because its arguments failed validation; its
128-token allowance differed from the app probe allowance. Corrected probes used
the app parser with a required path argument and 1,024 output-token allowance;
no returned file tool was executed. Both models passed before each attempt.
Provider-reported zero completion tokens are retained as reported, not inferred
as actual zero use. Included marginal estimates are not provider billing evidence.
