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
