# Development test performance

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

Fast intentionally covers only the five modules listed in CONTRIBUTING. Focused
patterns and the full integration gate remain necessary for controller and Git
changes. Treat the measured 267s full duration as evidence that a 90s agent check
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
