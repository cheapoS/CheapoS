# T26 — Benchmark optional test-output filtering

**Depends on:** T13, T24. **Size:** M. **Result:** the model can read a concise result while the operator and reviewer can recover original evidence.

## Read first

`Workspace.run_checks` spool/output limits, streamed check events, prompt/checkpoint construction, `commandMarkup`, gateway compression documentation linked in the check-in, and T24 benchmark/reporting.

## Implementation

1. Introduce separate raw-evidence and model-summary representations for check output. Exit status, command, duration, cancellation, truncation, and pass/fail remain controller-owned; filtering cannot rewrite them.
2. Current previews retain only a bounded excerpt and the temporary spool is removed. Add bounded task-owned raw-output retention/retrieval if required before claiming full output is available. Preserve existing output caps and clear truncation labels. Retrieval must resolve a known task/run ID, not an arbitrary filesystem path.
3. Start with one conservative standard-library unittest filter: retain run summary, failing test names, tracebacks, assertion details, and unknown/error lines; collapse repetitive passing-test lines. For unrecognized formats, retain the bounded original instead of guessing success.
4. Keep real live output visible in Details and provide raw-evidence access. Give the worker/reviewer a way to request omitted output. Do not transform tool arguments, source code, exact replacements, or reviewer decisions.
5. Keep filtering optional while measuring it. Check whether the selected gateway already compresses this payload; use one configured pass and record where it occurred. Do not install standalone RTK blindly when OmniRoute already supplies a compatible function.
6. Run the T24 fixtures with raw output and with filtering under otherwise comparable settings. Report payload-size/token estimates honestly; a byte reduction alone is not a measured provider-token or billing reduction. Include failures and retrieval overhead in the comparison.

## Acceptance

A failing traceback is recoverable exactly; ANSI/noisy success logs produce a concise summary; unusual output is not swallowed; all-failed/zero-tests/truncated/cancelled runs remain accurate. Raw retention is bounded and survives reload. Filtering never changes authorization or command execution. Results report task success, interventions, latency, and total usage where available.

## Validation / limits

Add output/parser/retrieval tests and a browser Details/raw-output scenario. Keep the experimental switch off by default unless the documented acceptance measurements justify promotion. No new shell proxy in the execution path, unbounded logs, silent double compression, or inference-cost claim based only on a small local string fixture.

## Completion record

Status: Done

- Behavior delivered: Bounded raw byte retention, safe task/run retrieval, raw viewer/download, worker/reviewer retrieval, and optional direct-local unittest summaries. Default remains off.
- Acceptance evidence: [Experiment and reproducible measurements](../experiments/output-filtering.md): all 24 controlled fixture runs verified; no reduction in short baseline logs; noisy retrieval increased overall payload.
- Commands and results: Focused filtering/verification/sample/stream tests: 23 PASS; raw capture/filter/HTTP tests: 8 PASS; JS: 70 PASS. An initial wrong module name was corrected; stop fixture now waits for request entry to remove a race.
- Browser scenarios and results: Isolated port 51032: noisy 44-test failure shows three tracebacks in Details/Checks; reload retains evidence, original-output dialog shows all 3,340 bytes and download action. Fixed binding when switching views.
- Remaining limitations: Two-MB/eight-run retention is bounded, older logs expire. No live token/billing measurements. Unknown gateway compression disables the local pass. UTF-8 display pagination may split a character; downloads retain exact bytes.

Before implementing, read [TASKS.md](../archive/TASKS.md) for the shared contract. Update this record and the matching board row when complete.
