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
