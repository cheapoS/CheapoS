# Contributing to cheapoS

Small, reviewable changes are welcome. For significant behavior changes, open an issue describing the problem and your proposed approach first.

## Fast iteration is the default

This is an actively developed private alpha. Run checks that exercise the change;
merging a small change does **not** require the entire regression suite. The
current policy here supersedes blanket full-gate instructions in historical task
cards. Preserve real failure, permission, persistence and Git coverage when those
behaviors change; do not weaken product safeguards to make checks faster.

New tests should be fast. Reuse existing integration coverage rather than adding
another expensive workflow for each small behavior. Before introducing a heavy
test, tell the operator its purpose, measured or estimated runtime, frequency,
and why a cheaper test is insufficient. Keep it proposed until the operator
accepts that cost. Examples include a full multi-item agent/Git run, real-time
waits, repeated expensive setup, or a material increase in routine check time.
Measure uncertain costs with the smallest representative fixture and report
new-test timing at handoff. Preserve meaningful assertions and product safeguards.

```sh
python3 -B scripts/check.py --plan          # inspect selection from working changes
python3 -B scripts/check.py                 # run selected checks, up to 4 processes
python3 -B scripts/check.py --base main     # include committed branch changes
python3 -B scripts/check.py --files dist/app.js dist/styles.css
```

The selector includes staged, unstaged, and untracked changes. Without `--base`,
a clean working tree runs nothing and says so. `--base main` includes changes
since the branch's merge base as well as current edits. `--files` overrides Git
detection. Unknown runtime files and Python files without known test coverage
select all Python modules visibly; inspect `--plan` before broad changes.
Selection follows static imports, including shared test helpers. Dynamic imports,
subprocess entry points, generated assets and behavior reached indirectly can
need additional focused tests; update the mapping in `scripts/check.py` when
adding such dependencies. This is a development aid, not a proof of complete
coverage or a replacement for the app's agreed verification command.

| Change | Iteration and normal merge checks |
| --- | --- |
| Documentation only | Local links/examples and `git diff --check`; no runtime suite |
| Frontend presentation | Changed-file command (JS syntax + JS tests), and the affected browser flow; no unrelated Python suite |
| One Python feature | Selected dependent tests; add a targeted scenario when static imports cannot identify the behavior |
| Permissions/controller | Affected authorization, execution and recovery modules plus relevant HTTP cases |
| Commit/reconciliation | Affected Git/evidence/recovery modules, retaining real repositories and failure cases |
| Test runner/selection | Runner/selector tests plus a representative real integration subset; a full run is not required merely because the runner changed |

For a tighter loop, explicitly name the relevant modules. Patterns can repeat and
overlap without running a test twice. Separate worker processes keep each test
module's setup/teardown together and isolate globals and mocks:

```sh
python3 -B scripts/dev_tests.py --pattern test_titles.py
python3 -B scripts/dev_tests.py --pattern test_branch_evidence.py --pattern test_branch_workspace.py --jobs 2 --timings
python3 -B scripts/dev_tests.py --suite fast
```

Use `--jobs 1` to debug serially, or reduce the worker count if local resources are
busy. `check.py` defaults to at most 4 workers; `dev_tests.py` keeps its existing
serial default and full selection when no selector is supplied, so existing
verification commands do not silently become weaker. Workers report failures,
import errors, crashes, skips and counts; empty discovery fails. Parallel timing
is wall time, so summed individual timings can exceed it. Ctrl+C cancels workers.

Use the complete suite for a release, an explicitly requested comprehensive
check, or broad backend changes whose effects cannot be bounded by focused
coverage. State the reason before choosing it. It is **not** a default step for
every commit, merge, documentation update or UI adjustment:

```sh
python3 -B scripts/check.py --full --jobs 4
# Python only, with a reusable timing report:
python3 -B scripts/dev_tests.py --suite full --jobs 4 --timings --json /tmp/cheapos-full.json
```

Once relevant checks pass, do not repeat them because work moved to review,
commit or merge. Recheck when conflicts or subsequent edits change the tested
behavior. Report exactly what ran, what did not, and any remaining uncertainty.

For UI behavior changes exercise the relevant flow with an isolated data directory
and deterministic provider. Record any unavailable browser check honestly; never
use personal task data or a live model as a fixture. Test HTTP servers need
loopback socket access. Automated fixtures inject zero cosmetic model pacing and
short HTTP shutdown polling; normal demos keep their 120ms step pacing.
See [test performance](docs/development/test-performance.md) for measurements.

Model execution tests use deterministic providers and temporary repositories,
with no external inference calls or personal API credentials.

For conversation changes, check live worker and reviewer output inside the cheapoS reply, command permission, reviewer revisions, and the final approval controls. Details should stay open through updates and tab switches; returning to Chat should show the latest message. Keep course corrections in chronological order and avoid presenting a failed or unfinished check/review as a success.

Preserve these properties:

- No hosted sign-in or required cloud project.
- No secrets in task records, configuration, browser storage, or test fixtures.
- Usage is reserved before a request and retained when billing is uncertain.
- Reviewer approval follows verification and refers to the actual task patch.
- Commands require the user's task-scoped approval; a snapshot is not described as a security sandbox.
- A provider error does not trigger a hidden retry or model upgrade.
- Savings claims require a measured baseline and comparable task outcomes.

Include what changed, why it helps, and relevant verification in your pull request. Do not commit `.cheapos/`, credentials, local task output, or unrelated generated assets. Code contributions are made under the repository's MIT license.
