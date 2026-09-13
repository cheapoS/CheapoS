# T11 — Measure test bottlenecks before optimizing

**Depends on:** none. **Size:** S. **Result:** a repeatable report identifies which tests and fixture work consume time.

## Read first

`tests/test_engine.py` (`LocalCase`, helpers), `tests/test_http.py`, `tests/test_gateways.py`, `tests/test_commits.py`, `Engine.fixture_response`, and CONTRIBUTING.

## Implementation

1. Add an optional standard-library timing runner, for example `scripts/dev_tests.py --timings`, using unittest discovery and a custom result class. Include setup/teardown in each test's wall time. Preserve skips, expected failures, subtests, failure output, and exit status.
2. Print a short summary: test count, pass/fail, total duration, and the slowest ten tests. Offer an explicit JSON report path for local comparison; no telemetry or committed machine-specific report by default.
3. Support discovery directory and filename pattern so profiling one module does not require running everything. Preserve the existing import-path behavior used by test helpers.
4. Measure one full suite on a quiet enough machine and record environment/command/duration in a concise `docs/development/test-performance.md`. Use broad machine context, not personal paths or identifiers. The previous 295.917-second run is a reference, not your newly measured result.
5. Examine the top slow cases: Git snapshot/setup, process startup, demo pacing, persistence, HTTP server shutdown, and waits. Separate observed timing from hypotheses. Do not claim a sleep is the bottleneck just because it exists.

## Acceptance

A deliberately failing temporary test returns a failing exit code; skips/subtests remain correct. Pattern selection works. Timing summary agrees with wall-clock total within reasonable overhead and includes fixture time. A full report is reproducible without external inference or credentials.

## Validation / limits

Test the runner on a tiny temporary suite before running the real full suite once. This card measures; it does not remove tests, disable persistence, change timeouts, parallelize the suite, or change CONTRIBUTING's required verification policy. Leave specific optimization recommendations for T12.

## Completion record

Status: Done

- Behavior delivered: Optional unittest timing runner with per-test fixture-inclusive times, full-suite total, slowest ten, explicit local JSON report, pattern/directory selection, and documented baseline.
- Acceptance evidence: Temporary failing/subtest/skip/expected-failure fixture preserves results and failure exit; test setup/teardown included. Full deterministic suite profiled with no external model calls.
- Commands and results: Runner regression passed; full timing run: 327 passed in 290.235s, zero failures/errors. Report summarized in docs/development/test-performance.md; diff check passed.
- Browser scenarios and results: Not applicable: development tooling only. Browser fixture idle during full profile.
- Remaining limitations: Per-test totals identify slow workflows but do not isolate fsync/Git/process shares. Module/class setup is represented in the overall suite total.

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
