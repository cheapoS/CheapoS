# Unattended qualification matrix — September 13, 2026

**Not qualified yet.** Six easy execution trials completed: two reached independently
verified feature commits; four paused. A separate document-planning attempt then
hit the provider's daily free-model quota. Medium, hard, and very-hard trials are
**unrun**, not passing. The latest fixes have deterministic regression coverage
but have not yet been requalified with live models.

## Conditions

- Explicit measurement mode: cumulative worker tokens, turns, requests, elapsed
  work, and check deadlines did not terminate these runs. Usage remained recorded.
- Free remote models through the user's OmniRoute gateway; $0 estimated spending
  policy, no paid or local fallback. Per-response output allowance remained 2,048
  tokens; network timeouts and nonprogress guards remained enabled. Thus these
  were uncapped cumulative-work trials, not unlimited individual responses.
- Execution proposals were operator-prepared. There were **zero operator
  interventions after Start** in each execution attempt. These results do not
  establish autonomous document/prompt-to-plan reliability.
- Every trial used a disposable committed source, independently supplied tests,
  a private task workspace, and an app-owned feature branch. No source was merged
  or pushed. Passing status required final review, real commit receipts, merge
  readiness, unchanged source main, and unchanged acceptance tests.

## Observed execution

Elapsed below is the app's accounted working time, excluding driver setup.
Complete counters, models, checks, receipts, and local evidence paths are in
[results.json](results.json).

| Batch / easy attempt | Result | Seconds | Requests | Worker tokens | Reviewer tokens |
| --- | --- | ---: | ---: | ---: | ---: |
| Diagnostic 1 | Ready for merge | 155.7 | 26 | 35,726 | 60,321 |
| Diagnostic 2 | Repeated reads; unfinished README | 108.3 | 17 | 63,334 | 0 |
| Diagnostic 3 | Ready for merge | 132.1 | 31 | 60,600 | 45,798 |
| Isolated v1 / 1 | Serialized command mistaken for absent executable | 71.6 | 20 | 79,780 | 0 |
| Isolated v1 / 2 | Invalid review evidence; eight-request cap | 107.9 | 26 | 46,834 | 50,785 |
| Isolated v1 / 3 | Serialized command mistaken for absent executable | 46.1 | 19 | 67,251 | 0 |

The diagnostic batch ran while another task changed the shared checkout. Its
two verified commits demonstrate completion, but it is not a controlled version
comparison. Diagnostic 1 lacks a recorded app SHA, and diagnostic 3 recorded a
different SHA at completion. Development and subsequent trials moved to the
isolated `work/unattended-trial-matrix` worktree.

Isolated v1 used `1569570`. Attempts 2–3 also record identical start/end hashes
of app Python modules. No core code changed during those three runs. New drivers
record the starting SHA and app hash before Start and verify the hash afterward.

Across execution: **139 requests, 353,525 worker tokens, 156,904 reviewer tokens**.
All reported costs are zero estimates; two execution requests retained uncertain
accounting. Token totals include repeated input context and do not represent
generated output alone. This small, failure-heavy sample cannot justify future
production budget defaults.

## Live defects and repairs

1. **Implementation stalls had no useful automatic handoff.** Commit `1569570`
   preserves the active item, files, usage and context, durably excludes failed
   workers, and uses a different eligible free model. Operator pause, missing
   information, setup, consent, hard limits, and branch drift remain excluded.
   Live isolated attempts 1 and 3 demonstrated a handoff followed by a README
   edit, but neither completed the run; do not count recovery activation as
   end-to-end success.
2. **A JSON-like command string poisoned verification setup.** Commit `0789ad3`
   rejects it as a correctable tool argument before changing the saved command.
3. **Review correction lacked actionable schema feedback.** The same commit
   supplies exact criterion keys and typed boolean/evidence fields; validation
   identifies missing, unexpected, or invalid criterion entries. Measurement
   item review no longer stops at eight requests. Persisted repeated-response
   detection still pauses after three identical unsuccessful rounds.
4. **Provider quota was hidden as a generic stream failure.** The follow-up
   change recognizes the daily-free-quota signal in HTTP-200 SSE errors, reports
   a provider-wide cooldown without inventing a reset time, and avoids probing
   sibling models on that exhausted provider. Raw account details are not shown.

## External blocker and planning

The separate easy document-planning attempt spent 94.1 seconds on four failed
route probes before producing any proposal. It recorded 9,544 reserved worker
tokens and four uncertain requests; these are not confirmed provider token
usage. It is an availability failure, not a completed planner quality test.

Local OmniRoute application logs at 21:17–21:19 UTC explicitly reported:
`Rate limit exceeded: free-models-per-day-high-balance.` All four candidates
belonged to the same OpenRouter connection. No reliable reset timestamp was
available. Additional execution requests were stopped, rather than mislabeling
provider quota failures as task difficulty failures.

## Validation and integration

- Worker recovery: 4 focused tests, 9.4 seconds; routing: 25 tests, 9.5 seconds.
- Review, evidence, and measurement: 16 tests, 32.9 seconds. Includes real checks,
  a review beyond eight distinct reads, durable repeated-failure detection, and
  prevention of malformed commands changing setup state.
- Quota handling: 3 focused tests, 0.45 seconds. Includes shared-provider probe
  suppression and continued eligibility of a different provider.
- Baseline acceptance tests fail on each incomplete fixture as intended.
- Latest main `3c0f66f` merged cleanly into this branch at `540786f`, bringing the
  requested test-performance improvements. No full suite was rerun for the merge.

## Resume qualification

Once free-model requests are available, run three fresh easy trials on the fixed
revision, then three medium, three hard, and three very-hard trials. Preserve
failures; stop progression to repair repeated app defects. Use a new result root
for each code revision, and never modify loaded app code while a trial is active.

Example from this worktree:

```sh
python3 -B docs/trials/matrix/run_live.py easy 1 --live --root /tmp/cheapos-matrix-v2-20260913
```

Fixtures cover whitespace/type handling; CSV/Decimal validation and reports;
a persistent HTTP task app plus browser client; and a multi-item SQLite migration,
atomic import/export, and CLI. The hard fixture also requires a real browser
add/complete check after generated code passes its independent API/client tests.
These are controlled difficulty levels, not a claim to cover every large project.

Document and chat-prompt planning must be assessed separately before claiming
full input-to-delivery success. No higher-level completion or budget recommendation
is supported by the results so far.
