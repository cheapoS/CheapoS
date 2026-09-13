# Independent report acceptance contract (T42, version 1)

This pack is separate from ordinary `tests/` discovery. It requires only installed
Python and the real repository package; no credentials, model, Git repository,
external fixtures, sleeps or branch execution. Records are synthetic projections
of saved fields, not cryptographically revalidated Git evidence. Export is a
read-only account of saved receipts, not a new signature or billing lookup.

The implementation API is `cheapos.run_report.render_run_report(task) -> str`.
Invalid/non-run or unsupported-schema input raises ValueError or TypeError. The
endpoint is `GET /api/tasks/<id>/run-report`. Header contract is
`attachment; filename="cheapos-run-<validated-id>.md"`; never a title-based name.
Formatting may vary, but labels must identify unavailable/unknown/not-recorded
values and distinguish confirmed integration from incomplete receipts.

## Agreed executable checks

Run from a clean copy of the repository root, including these independent files:

```sh
python3 -B scripts/dev_tests.py --directory docs/trials/run-report-acceptance --pattern test_formatter_acceptance.py
python3 -B scripts/dev_tests.py --directory docs/trials/run-report-acceptance --pattern test_endpoint_acceptance.py
```

The first command belongs in Item 1 and final checks. The second belongs in Item 2
and final checks. Keep them as separate exact program/argv commands in the
inspected proposal. The existing runner adds the real repository root to imports;
calling a test from an arbitrary directory without it is not equivalent.
`example.make_example()` is runnable code using synthetic saved data and is
executed by the formatter check. It calls the actual public formatter.

Before Start and after completion, the observing driver runs:

```sh
python3 -B docs/trials/run-report-acceptance/selfcheck.py --verify
```

Capture DIGEST.json and compare **both its saved bytes and every listed file hash**
outside worker control before/after Start. The pack hash is SHA256 of compact,
key-sorted JSON mapping filename to SHA256. `--digest` computes, but does not alter,
the manifest. Do not merely trust a worker-rewritten manifest. A changed pack or
example disqualifies that attempt; retain its result and fix only before a new
proposal. This cannot be replaced by post-readiness observer checks.

## Source fields and discriminating checks

| Requirement | Actual saved fields and rule | Executable coverage |
| --- | --- | --- |
| Supported input | `branch_run.schema_version == 1`, compatibility from branch_runs | invalid_inputs; HTTP unknown/interactive/unsupported |
| Run identity and refs | `branch_run.id`, `feature_ref`, `target_ref` (not feature_branch) | real_schema_determinism_allowlist_and_example |
| Ordered items | `branch_run.items[].title/status`; preserve order | markdown_unicode_order_and_typed_pause |
| Confirmed commit | item status committed AND commit_receipt stage completed, matching run_id/item_id, valid new_tip SHA | stale_mismatched_and_unfinished_commit_receipts |
| No-change outcome | status and receipt.outcome satisfied_without_change; no SHA/count invented | no_change_creates_no_commit |
| Integration | merged plus completed merge_receipt whose mapping.run_id and feature_tip/target_ref identify this run/target | outcomes_and_merge_receipt_identity |
| Checks and review | task.checks[].passed; task.checkpoints[].decision; absent arrays unknown, not passed | real_schema and missing_partial tests; check labels inspected at T45 |
| Model IDs | task.providers.worker/reviewer.model; omit credential/endpoint siblings | real_schema allowlist sentinel |
| Tokens/cost/time | task.usage.worker/reviewer.tokens, usage.cost/estimated_requests/uncertain_requests; branch_run.consumption.working_seconds; missing role remains unavailable | missing_partial_zero_and_uncertain_accounting; real_schema |
| Pause | branch_run.pause_reason, no raw diagnostic payload | markdown_unicode_order_and_typed_pause |
| Exclusions | no prompt, inputs/document, instructions, messages, patch, feedback, test output, auth ref, source/workspace, credentials/endpoint | private_absent sentinel and unchanged deep copy |
| Markdown/Unicode | escape pipe and heading/newline injection while preserving Unicode text | markdown_unicode_order_and_typed_pause |
| HTTP download | saved Store.get copy, UTF8 text, fixed safe attachment, bounded 4xx, origin guard | both endpoint tests |
| No side effects | fail-closed engine/store; subprocess.Popen forbidden; deep-equal original records | download_repeated_safe_headers_and_no_side_effect |

Schema sources inspected: cheapos/branch_runs.py new_run/compatibility;
branch_commits.py prepare/finish; branch_merge.py prepare/finish;
branch_completion.py saved merge_receipt; branch_evidence.py immutable JSON
candidate receipt; storage.py Store.get; metrics.py aggregate;
dist/branch_ui.js projectRun. A report does not call receipt revalidation because
that reads the current workspace/Git and changes the meaning of a saved snapshot.
The synthetic commit record uses only the saved presentation projection. It is
not a fake proof suitable for branch execution.

## Independent checks and limits

`python3 -B docs/trials/run-report-acceptance/selfcheck.py` validates the current
fixture schema and tests six deliberately bad output fragments: invented branch
field, missing confirmed SHA, stale SHA, private text leakage, missing accounting
as zero, and Markdown injection. These are assertion negative controls, not a
mock exporter passed off as implementation validation. Endpoint import/runtime
will be exercised against the actual feature once implemented.

T45 browser scenarios remain unverified here: keyboard reachability and actual
browser download for paused/ready/merged/left-on-branch; no export in Interactive;
unchanged composer draft/open Details and Pause/proposal/revision/merge controls.
These must be recorded separately, not inferred from HTTP tests. Endpoint fixture
requires loopback binding permission. No expensive full-run fixture is introduced.
