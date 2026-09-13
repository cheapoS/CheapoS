# T12 — Fast/focused/full checks and measured fixture improvements

**Depends on:** T11. **Size:** M. **Result:** developers and agents can verify a small change quickly without losing the full integration suite.

## Read first

T11 report/runner, CONTRIBUTING, test fixture helpers, scripted provider pacing, and the slow tests identified by actual measurements.

## Implementation

1. Add explicit fast, focused, and full test selections to the development runner. A suggested CLI is `python3 -B scripts/dev_tests.py --suite fast|full` plus `--pattern test_permissions.py`. Document exactly what each includes; no silent exclusion of slow failures.
2. Keep fast tests for pure logic, argument parsing, presentation, and policy. Keep real Git, subprocess, HTTP, restart, and end-to-end tests in integration/full. If an existing test mixes concerns, split only the part needed to make that boundary clear.
3. Remove measured test-only overhead. Example: inject configurable demo pacing so UI demos keep their readable delay while automated scripted fixtures use zero delay. Do not globally monkeypatch time.sleep or weaken production behavior.
4. Replace unnecessary polling/setup only where profiling justifies it. Preserve real process cancellation, atomic persistence, restart recovery, and commit conflict cases. Do not reuse a mutable repository across tests without proven isolation.
5. Update CONTRIBUTING with a change-to-check mapping: documentation, frontend presentation, permissions/controller, and Git commit/reconciliation. Require focused checks during iteration and the complete relevant gate once before integration/release. Explain when browser verification is required and how to record unavailable checks.
6. Keep a full-suite command that runs every required test. Document that a docs-only reference update needs link/format checks, not an unrelated five-minute runtime suite.
7. Compare before/after on the same environment, report counts and failures as well as duration. Initial goals: fast under ten seconds, common focused checks under thirty seconds; full toward two minutes. Record actual results if those targets are not achieved.

## Acceptance

The full suite still covers all prior contracts; fast/focused/full exit codes are reliable. Deliberately injecting a relevant failure is caught by the documented selection. The profiling report shows what improved and why. Repeated unchanged passing tests are not mandated just because work moved from editing to review.

## Validation / limits

Run focused checks during changes, then one full suite and a representative browser workflow. No new test framework, paid/live model calls, blanket fsync removal, weakened timeouts, or parallel execution unless measurements and isolation specifically justify it. If optimizing more than two unrelated bottlenecks is necessary, defer the extra optimizations to follow-ups.

## Completion record

Status: Done

- Behavior delivered: Explicit fast/focused/full selections; test-only zero demo pacing injection and shorter HTTP shutdown polling; change-to-check CONTRIBUTING policy; measured comparison.
- Acceptance evidence: Deliberate temporary failures are caught by fast/full selection. Full still discovers every test module and preserves Git/process/persistence coverage. Standard browser demo still reaches checks/review with normal pacing.
- Commands and results: Runner regressions: 2 passed; fast: 50 passed in 0.014s (0.069s separate CLI wall time); full: 328 passed in 267.283s; 62 JavaScript tests, syntax, and diff checks passed.
- Browser scenarios and results: Restarted disposable fixture using updated Engine; normal scripted demo reached passed checks and independent approval with final human decision still required.
- Remaining limitations: Full suite improved about 7.9% in one comparison but remains above the two-minute target. Larger verification allowance is required in T13; no further unmeasured optimizations added.

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
