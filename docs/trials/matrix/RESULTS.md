# Unattended qualification matrix — September 13, 2026

**The trial batch is complete; the feature is not broadly qualified.** Across
30 execution attempts (including two generated-plan continuations), 18 reached
app readiness and 12 paused. Independent checks disproved three of those ready
results. Historical diagnostic runs also have the provenance limits noted below.

Antigravity and Kiro completed the very-hard fixture. Chat and document inputs
both completed easy work through verified commits with no intervention after
Start. NVIDIA/Kiro completed medium, but its hard attempt stalled with invalid
Python and a request for file contents already available through its tools.

Recorded execution totals: **695 requests, 4,123,291 worker tokens, 2,132,306
reviewer tokens**, including four uncertain request reservations. Planning usage
is separate. These totals include repeated input context, failed attempts, and
multiple code revisions; they are not clean model benchmarks or invoiced costs.
Detailed measurements and failures are retained in [results.json](results.json)
and [included-evidence.json](included-evidence.json).

## Conditions

- Explicit measurement mode: cumulative worker tokens, turns, requests, elapsed
  work, and check deadlines did not terminate these runs. Usage remained recorded.
- The original OpenRouter cohort used free remote models through the user's OmniRoute gateway; $0 estimated spending
  policy, no paid or local fallback. Per-response output allowance remained 2,048
  tokens; network timeouts and nonprogress guards remained enabled. Thus these
  were uncapped cumulative-work trials, not unlimited individual responses.
- Included-connection trials pin a worker/reviewer pair. Their catalog prices are
  unknown, so they are not automatically eligible free routes. Private profiles
  use zero marginal estimated rates based on included access, not published token
  prices. User global settings are unchanged. From `0cb00fe`, zero-rate measurement
  omits the application output cap; provider defaults and transport guards remain.
  Account-wide quota readings are observations, not exact per-trial attribution.
- Twenty-eight execution attempts used operator-prepared proposals. Two used
  model-generated proposals inspected before Start. There were **zero operator
  interventions after Start** in every attempt. The two generated-plan successes
  establish the easy input paths only, not general planning reliability.
- Every trial used a disposable committed source, independently supplied tests,
  a private task workspace, and an app-owned feature branch. No source was merged
  or pushed. App readiness required final review, real commit receipts, merge
  readiness, unchanged source main, and unchanged acceptance tests.

## Original OpenRouter execution

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

Across the original six execution attempts: **139 requests, 353,525 worker tokens, 156,904 reviewer tokens**.
All reported costs are zero estimates; two execution requests retained uncertain
accounting. Token totals include repeated input context and do not represent
generated output alone. This small, failure-heavy sample cannot justify future
production budget defaults.

## Included connection observations

These are controlled fixtures and different pinned model pairs, not repeated
same-model statistical measurements. Some profiles ran concurrently. Reported
zero costs are marginal estimates for included access, not provider invoices.

| Profile | Easy | Medium | Hard | Very-hard |
| --- | --- | --- | --- | --- |
| Antigravity Sonnet / Opus | Passed | Attempts 1–2 passed; attempt 3 stopped at quota during final review | Passed + browser verified | Passed 8/8 supplemental checks after automatic CLI repair |
| Kiro Sonnet / Haiku | Passed after coverage fix | Attempt 3 passed all 9 checks including runnable README; earlier failures retained | Passed + browser verified | Fresh retry passed all 8 tests after two preserved failures |
| NVIDIA Nemotron / Kiro Haiku | Passed | Fresh retry passed 8/8 + README; original approval failed 3/8 | Failed: indentation error, asked for available file contents | Unrun after hard failure |
| NVIDIA Nemotron / NVIDIA Gemma | Worker implementation passed, reviewer stalled | Unrun | Unrun | Unrun |

The original NVIDIA attempt also hit the app's 2,048 output cap before the
provider-default correction. Failed attempts are preserved, not replaced.

The most costly observed medium attempt was NVIDIA/Kiro: 883.6 seconds elapsed,
860.9 seconds in provider requests, only 1.14 seconds in checks. Its reviewer
incorrectly claimed `.2f` formatting on Decimal was invalid. The original commit
formatted `9007199254740993.01` exactly; following the suggested float conversion
changed it to `9007199254740994.00`. Final approval missed this regression. Stronger
future acceptance tests now cover large exact amounts, excess fractional zeros,
and quoted CSV newlines. Existing source fixtures were never rewritten.

Kiro chat prompt planning took 7.96 seconds (one request), then execution took
50.10 seconds (10 requests). Document planning took 7.59 seconds (one request),
then execution took 50.59 seconds (11 requests). Both exact generated proposals
were inspected, refreshed without contract changes, and authorized once; both
finished with real commits and unchanged independent tests. This is evidence for
the easy input-to-delivery paths, not all difficulty levels of planning.

Account-wide quota snapshots at 18:42 EDT showed Antigravity Claude 0% remaining,
Antigravity Gemini 93% remaining, and Kiro 15.93/50 credits used. NVIDIA quota was
not exposed by this dashboard; no NVIDIA exhaustion was demonstrated. Concurrent
user activity may contribute. Exhausting one model pool does not exhaust every
model or connection.

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

5. **App output caps defeated cumulative measurement.** `0cb00fe` omits
   `max_tokens` for zero-rate measurement work while retaining usage accounting,
   monetary controls, provider defaults, and transport safety limits.
6. **Final coverage mistakes had no correction round.** `1aec09c` supplies exact
   coverage schemas and durable, specific correction feedback. Live Antigravity
   and Kiro trials recovered from these mistakes without operator intervention.
7. **Empty default read calls were rejected.** `c559aa8` accepts an empty argument
   string only for `list_files` and `get_diff`. Executable tools and malformed
   argument objects remain rejected. Kiro's saved calls demonstrated this issue;
   the upstream model/gateway origin cannot be determined from retained data.
8. **Final diff review lacked criteria and check context.** The same commit adds
   compact bound evidence to every chunk, preserving exhaustive receipts and the
   packet size guard. Reviewers must explain a concrete failure when contradicting
   passing checks; checks still do not prove full correctness. This reduces missing
   context, but does not guarantee reliable model judgment.

9. **Background criteria were mistaken for per-chunk coverage.** The first live
   multi-chunk Kiro run after `c559aa8` repeatedly requested already-present CLI
   evidence from later chunks. It stopped after three no-op repair cycles.
   `59fc08c` explicitly distinguishes global background, partial chunk review,
   and whole-plan synthesis. It preserves rejection of concrete defects and
   exact coverage validation. Two targeted isolated tests passed in 8.17 seconds.
   Kiro very-hard attempt 3 then passed live: 31 requests, 189.0 seconds, three
   real item commits, all eight acceptance tests and final chunks approved.
   The failed attempt used 53 requests and 329.6 seconds without readiness.

10. **Structured quota errors were still generic.** Antigravity medium attempt 3
    stopped during final review with upstream HTTP 429 and a gateway cooldown of
    4h 14m 53s. The dashboard showed Claude at 0%; Gemini retained 93%.
    `b27bd46` recognizes the gateway's structured SSE rate-limit fields and
    reports a model-route cooldown without excluding unrelated model pools.
    Raw SSE was not retained; the replay uses the installed gateway serializer's
    shape. Two focused offline tests passed in 0.006 seconds. This reporting fix
    was not requalified with another live exhausted-quota request.

A catalog-listed `kiro/claude-sonnet-5` reviewer returned HTTP 400 on its first
hard-trial review request. The gateway logged "Invalid model" and its internal
fallback also failed. Catalog presence is not proof of a usable inference route.
This attempt remains a recorded route failure, not a quota failure.

The executable README check caught Kiro medium attempt 2: unquoted commas in
the documented CSV made its example fail. Future medium fixtures explicitly
require a runnable fenced Python example and execute it as a ninth test. This
new format requirement is not retroactively applied to historical indented
examples that were independently executed successfully.

## Original OpenRouter blocker and planning

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
- Output defaults: 2 focused tests, 0.11 seconds.
- Tool arguments: 6 focused tests, 1.39 seconds; final review: 9 tests, 36.02 seconds.
- Baseline acceptance tests fail on each incomplete fixture as intended.
- Latest main `3c0f66f` merged cleanly into this branch at `540786f`, bringing the
  requested test-performance improvements. No full suite was rerun for the merge.

## Remaining qualification work

The batch contains at least three observations at each difficulty, but mixes
models, revisions, and fixture improvements. It does not establish production
success rates or justify restrictive default budgets. Original plans, fixtures,
failures, commits, and supplemental checks remain available by evidence path.

Use Antigravity/Kiro results to guide the next controlled real-project trial.
NVIDIA's tested pair is not qualified for hard unattended work. Automatic routing
among included subscription accounts remains unqualified: these trials used
explicit pinned pairs because the gateway did not publish eligible zero pricing.
A catalog-listed route also proved unusable, so catalog presence must not be
confused with successful tool-capable inference.

No feature branches from trial projects were merged or pushed. App fixes and
reports are committed on `work/unattended-trial-matrix`, separately from the
shared checkout. The requested latest main test improvements were incorporated;
focused offline regressions were used instead of a full expensive suite.
