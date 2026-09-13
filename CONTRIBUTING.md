# Contributing to CheapOS

Small, reviewable changes are welcome. For significant behavior changes, open an issue describing the problem and your proposed approach first.

Choose checks for the changed behavior while iterating:

| Change | Focused validation |
| --- | --- |
| Documentation only | Check local links, examples, and `git diff --check`; no unrelated runtime suite |
| Frontend presentation | `node --check dist/app.js`, `node --test tests/test_*.js`, and the affected browser flow |
| Pure utilities/title/test-profile policy | `python3 -B scripts/dev_tests.py --suite fast` plus the changed module if not in fast |
| Permissions/controller | `python3 -B scripts/dev_tests.py --pattern test_permissions.py`, affected project-permission/review/recovery modules, and HTTP coverage for API changes |
| Commit/reconciliation | `python3 -B scripts/dev_tests.py --pattern test_commits.py` plus affected review/rollback tests; retain real Git fixtures |
| Test runner/fixtures | `python3 -B scripts/dev_tests.py --pattern test_dev_tests.py`, affected fixture modules, then full before integration |

Use `--pattern test_x.py` for each relevant Python module. The **fast** suite
contains `test_titles.py`, `test_test_profiles.py`, `test_time_ago.py`,
`test_word_count.py`, and `test_csv_to_md.py`: small policy/utility tests without
Git or HTTP fixture setup. It does not replace integration coverage.

Before integrating a behavior change or releasing, run the complete gate once:
`python3 -B scripts/dev_tests.py --suite full --timings`,
`node --check dist/app.js`, and `node --test tests/test_*.js`. Full discovers all
`test_*.py` modules, including real Git, processes, HTTP, persistence, restart,
and end-to-end scenarios. The original unittest discovery command remains valid.
Do not repeat unchanged passing checks merely because work moved to review or
human approval; rerun when code or relevant inputs change.

For UI behavior changes exercise the relevant flow with an isolated data directory
and deterministic provider. Record any unavailable browser check honestly; never
use personal task data or a live model as a fixture. Test HTTP servers need
loopback socket access. Automated fixtures inject zero cosmetic model pacing and
short HTTP shutdown polling; normal demos keep their 120ms step pacing.
See [test performance](docs/development/test-performance.md) for measurements.

Model execution tests use deterministic providers and temporary repositories,
with no external inference calls or personal API credentials.

For conversation changes, check live worker and reviewer output inside the CheapOS reply, command permission, reviewer revisions, and the final approval controls. Details should stay open through updates and tab switches; returning to Chat should show the latest message. Keep course corrections in chronological order and avoid presenting a failed or unfinished check/review as a success.

Preserve these properties:

- No hosted sign-in or required cloud project.
- No secrets in task records, configuration, browser storage, or test fixtures.
- Usage is reserved before a request and retained when billing is uncertain.
- Reviewer approval follows verification and refers to the actual task patch.
- Commands require the user's task-scoped approval; a snapshot is not described as a security sandbox.
- A provider error does not trigger a hidden retry or model upgrade.
- Savings claims require a measured baseline and comparable task outcomes.

Include what changed, why it helps, and relevant verification in your pull request. Do not commit `.cheapos/`, credentials, local task output, or unrelated generated assets. Code contributions are made under the repository's MIT license.
