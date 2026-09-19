# Development test performance

## Current iteration workflow (September 13, 2026)

Start with `python3 -B scripts/check.py --plan`, then run the command without
`--plan`. It selects checks from working changes; add `--base main` to include
committed branch changes. UI changes run JavaScript syntax checks and tests,
with no Python suite. Documentation changes run a whitespace check only.
See [CONTRIBUTING](../../CONTRIBUTING.md) for selection limits and the current
policy: focused validation is sufficient for routine iteration and merges.
Full regression is an explicit release/broad-change choice, not a default gate.

The Python runner accepts repeated `--pattern` options and `--jobs 2` (up to 16).
Workers use isolated processes, with each module's fixtures kept together.
The existing runner still defaults to full serial execution; use `check.py` for
automatic selection. No application verification command or safeguard changed.

### Bounded measurements

Darwin arm64, Python 3.9.6; both integration runs used the same 17 tests from
`test_branch_evidence.py` and `test_branch_workspace.py`, with zero failures,
errors or skips:

| Selection | Workers | Runner wall time |
| --- | ---: | ---: |
| Evidence + workspace | 1 | 47.154s |
| Evidence + workspace | 2 | 32.926s |

That is 30.2% less elapsed time in this local comparison. It is not a measured
speedup for the complete suite; machine load and module balance affect results.
Reports were written to `/tmp/cheapos-validation-serial.json` and
`/tmp/cheapos-validation-parallel.json` (local, not committed).

The frontend command passed all 88 JavaScript tests (83ms reported by Node),
plus syntax checks, without selecting Python tests. Runner/selector regression
checks passed 11 tests, covering selection, real Git changes, overlapping
patterns, concurrent process isolation, failures, crashes and import errors.

Profiling a cumulative final-review case found 553 subprocess calls in 16.482s;
subprocess work accounted for 97.7% of its time, while the actual Python check
used only 0.014s. Reusing the readiness manifest already returned by the tested
operation and removing one duplicate validation reduced it to 459 subprocesses
and 12.585s (23.6% less time). Assertions and real Git checks remain intact.
All six final-review tests passed in 80.053s after this test-only adjustment.
Production evidence freshness and persistence behavior were not changed.

### Subprocess batching, module partitioning, and LPT parallel scheduling (September 13, 2026)

Profiling `test_commits.py` found 342 subprocess calls in 9.149s for a single
test, with subprocess execution accounting for 94.1% of test duration.
Marker queries in `commits.py` (`source_state`) and `branch_merge.py` (`_clean`)
were batched from 6 sequential `git rev-parse --git-path <marker>` calls into a
single batched invocation. Precomputed `evidence_identity` hashes were reused
across consecutive matching calls in `needs_patch_review` and `reviewed_patch`.

`parallel_tests.py` now implements Longest Processing Time (LPT) queue
scheduling, dispatching known heavy modules (`test_commits`, `test_branch_*`)
first so short tests backfill worker capacity rather than leaving idle workers
waiting on long-tail modules. `check.py` defaults to `min(8, os.cpu_count() or 1)`
workers.

The monolithic `test_commits.py` (previously 26 tests, 120.9s serial) was
partitioned into three independent modules: `test_commits.py` (core commit
behavior), `test_commit_reconciliation.py` (reconciliation logic), and
`test_commit_recovery.py` (crash and ref failure recovery), allowing them to run
concurrently.

| Selection | Workers | Before | After | Wall-clock reduction |
| --- | ---: | ---: | ---: | ---: |
| Single followup commit test | 1 | 9.149s | 6.794s | 25.7% |
| Complete 26 commit tests | 3 | 120.899s (serial) | 46.329s (parallel) | 61.7% |
| Selection + runner + commits + merge (44 tests) | 6 | — | 61.350s | All passing |

The complete suite was deliberately not rerun for this tooling change. The
measurements below are historical snapshots with different test counts, not
current mandatory gates or timeout recommendations.

## Historical timing runner and baselines

Use the optional standard-library timing runner from the repository root:

```sh
python3 -B scripts/dev_tests.py --timings --json /tmp/cheapos-test-timings.json
python3 -B scripts/dev_tests.py --pattern test_permissions.py --timings
```

The JSON destination is explicit and local; nothing is uploaded. Per-test wall
times include `setUp` and `tearDown`. Class/module fixture overhead and runner
reporting are included in the suite total, but are not attributed to an
individual test. Normal unittest failures, subtests, skips, expected failures,
and exit status are preserved. A filename pattern selects discovery without
changing test-helper import behavior.

The September 13 check-in's 295.917-second result is historical context, not a
measurement made by this runner. Compare counts, outcomes, Python/OS, and the
same selected tests before interpreting a duration difference. Local machine
load also affects these results.

## Baseline

Measured September 13, 2026 on Darwin arm64, Python 3.9.6, with the command above and loopback socket access enabled. The browser fixture was idle. **327 tests passed in 290.235 seconds**; 0 failures, 0 errors. Raw machine-local report: `/tmp/cheapos-t11-baseline.json` (not committed).

| Slowest test | Seconds including fixture work |
| --- | ---: |
| `test_http.HTTPTests.test_commit_api_requires_preview_and_explicit_same_origin_approval` | 9.763 |
| `test_commits.CommitTests.test_followup_commits_only_the_next_patch` | 7.509 |
| `test_commits.CommitTests.test_add_add_reconciliation_keeps_both_versions_and_commits_only_after_new_review` | 6.981 |
| `test_commits.CommitTests.test_decline_saves_the_patch_and_blocks_stale_approval_until_reopened` | 6.040 |
| `test_compact_edits.CompactRecoveryTests.test_bad_saved_command_recovers_from_explicit_automatic_and_resumed_checkpoints` | 5.899 |
| `test_commits.CommitTests.test_failed_ref_update_preserves_staged_patch_and_recovers_after_restart` | 5.457 |
| `test_commits.CommitTests.test_patch_or_head_changes_invalidate_preview` | 5.308 |
| `test_http.ProviderTests.test_full_workflow_through_chat_completions_http` | 4.917 |
| `test_http.ProviderTests.test_full_workflow_through_omniroute_gateway_http` | 4.903 |
| `test_review_workflow.ReviewWorkflowTests.test_finished_edit_automatically_reaches_review_and_followups_remain_open` | 4.590 |

Module totals (sum of per-test durations):

| Module | Seconds |
| --- | ---: |
| `test_commits` | 89.453 |
| `test_http` | 39.301 |
| `test_model_pool` | 21.876 |
| `test_routing` | 21.787 |
| `test_compact_edits` | 18.966 |
| `test_answer_recovery` | 14.367 |
| `test_permissions` | 11.781 |
| `test_chat` | 11.202 |

## Interpretation and next measurements

Observed: Git commit/reconciliation workflows and HTTP end-to-end workflows
are prominent among the slowest cases. These exercise real snapshots, processes,
atomic persistence, and multiple model-fixture steps. The report measures their
combined wall time; it does not attribute an individual share to fsync, Git,
process startup, or network teardown.

Two bounded T12 experiments are justified: remove the scripted provider's
cosmetic 120ms pacing from automated fixtures through explicit injection, and
reduce the HTTP fixture server polling interval so shutdown does not wait for
the default half-second polling boundary. Keep production pacing and real
Git/process/persistence/cancellation coverage. Compare the full suite on this
same environment afterward. Defer persistence changes and parallel processes
until more detailed profiling warrants them.

## T12 comparison

Same Darwin arm64 / Python 3.9.6 environment; no external inference. Automated
`LocalCase`/HTTP fixtures now explicitly request zero cosmetic provider pacing.
HTTP/gateway fixture servers use a 10ms shutdown polling interval. Production
demos keep the 120ms default, and no persistence, Git, cancellation, or restart
tests were removed.

| Selection | Tests | Result | Runner time |
| --- | ---: | --- | ---: |
| T11 full baseline | 327 | Pass | 290.235s |
| T12 full | 328 | Pass | 267.283s |
| T12 fast | 50 | Pass | 0.014s |

The extra full-suite test verifies fast/full selection catches injected failures.
A separate fast CLI invocation took 0.069s including process startup/discovery.
Full-suite duration decreased by 22.952s
(7.9%) in this pair of runs. This is
one local comparison, not a cross-machine performance guarantee. The two-minute
full-suite target was **not achieved**. Git/persistence-heavy scenarios still
dominate; further changes need more detailed profiling, not reduced coverage.

| Module | Baseline | After |
| --- | ---: | ---: |
| `test_http` | 39.301s | 22.371s |
| `test_commits` | 89.453s | 87.069s |
| `test_gateways` | 0.810s | 0.290s |
| `test_permissions` | 11.781s | 11.855s |

Commands:

```sh
python3 -B scripts/dev_tests.py --suite fast --timings
python3 -B scripts/dev_tests.py --pattern test_permissions.py --timings
python3 -B scripts/dev_tests.py --suite full --timings --json /tmp/cheapos-test-timings.json
```

Fast intentionally covers only the five modules listed in CONTRIBUTING. At that stage, focused
patterns and a full integration gate were required for controller and Git
changes; the current policy above supersedes that requirement. Treat the measured 267s full duration as evidence that a 90s agent check
timeout is insufficient; T13 must provide a bounded larger allowance when the
full suite is deliberately selected.

## Final T01–T27 integration gate

The completed branch passed **387 tests in 428.861 seconds**, with no failures,
errors or skips, on the same macOS arm64/Python 3.9.6 environment. The enlarged
suite includes benchmark, verification-identity, continuation, readiness and
recovery coverage. This run is not directly comparable to T12's smaller suite.
The full-suite two-minute target remains unmet; use a 600-second check allowance
for this gate. The slowest scenario was the seven-fixture benchmark (25.859s).
JavaScript: 70 tests passed. No unchanged passing gate was repeated after the
final documentation update.

## Restart preparation with accumulated task history (2026-09-19)

On macOS/Python 3.9, a temporary copy of a 103-task profile (about 124 MB of
task records) took 2.621 seconds for Engine construction plus continuation
restoration. Selecting only the fields required by permission registration,
integration restoration and settings restoration reduced this to 0.494 seconds.
Both measurements disabled Club sync, credential lookup and work dispatch; they
measure local startup preparation, not the entire browser/provider reconnect.
The original profile and running tasks were untouched.

Gateway shutdown no longer waits up to five seconds for a daemon catalog probe.
The closed flag prevents late probe results or new process launches; the saved
keep-running preference still controls cleanup of an owned gateway process.
An isolated server's real restart acknowledged immediately and reconnected with
a new request token in 0.566 seconds, including the existing 0.4-second delay.
Server output now records shutdown, saved-work loading and continuation timings
without task contents or credentials, to distinguish any remaining delays.

Five new deterministic cases in `tests/test_restart.py` took 0.007 seconds
together. They reject unnecessary history copying, check detached metadata,
retain permission and continuation behavior, and simulate late catalog results
without real network requests or waits. Existing focused coverage was reused;
no new heavy restart benchmark was added to the normal suite.
