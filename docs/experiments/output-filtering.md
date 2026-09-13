# Optional unittest output filtering

Decision (2026-09-13): **keep off by default**. Seven fixed T24 fixtures passed
in all three modes but logs were too short for a useful reduction. A noisy
variant showed smaller requests, then one raw retrieval made total payload larger
than baseline. This does not justify a default or a billing-savings claim.

## Implementation and activation

For new tasks only, explicitly start cheapoS with
`CHEAPOS_CHECK_OUTPUT_FILTER=unittest python3 run.py`. Unset that variable for the
default. Each task freezes its selection. Only direct loopback Ollama requests
are eligible; gateway/automatic/other remote routes stay unfiltered because their
compression configuration is not established. Direct local needs no dependency.

Unfiltered live output and the 32 KB preview remain visible. The latest eight
check runs retain up to 2,000,000 original bytes each in the task's private data
directory, outside its source workspace. Older output expires; previews stay.
Raw truncation is separate from preview truncation. The process output cap,
approval rules, exit status, duration, pass/fail, cancellation and evidence
identity remain controller-owned.

Checks and conversation Details open the retained raw viewer. Its download
preserves exact bytes; the display decodes UTF-8. Both model roles can request
`read_check_output(run_id, offset)`, 8,000 bytes per page. IDs must resolve a
known task/run, never an arbitrary path. Missing/expired evidence errors clearly.
Byte pagination can split a UTF-8 character; the original download is exact.

The optional pass works only on known check objects in structured message data.
It never rewrites source strings, requests, exact edits, schemas, or decisions.
It collapses strictly recognized passing unittest rows only when a run-summary
line exists and the result is actually shorter. All failure/unknown lines remain.
Unrecognized, zero-test and preview-truncated output stays original. Only the
latest retained checks can be summarized. The request metric records layer,
before/after message bytes, omitted rows and processing time. Stored evidence
and messages remain original.

OmniRoute's [versioned RTK documentation](https://github.com/diegosouzapw/OmniRoute/blob/release/v3.8.51/docs/compression/RTK_COMPRESSION.md)
describes processing captured tool output, not controlling the client process.
The installed 3.8.49 gateway is a different version; compatible active filtering
cannot be inferred. No RTK binary, proxy or gateway pass was installed/enabled.

## Reproduction and measurements

`python3 -B scripts/output_filter_benchmark.py --output /tmp/output-results.json`

Python 3.9.6, macOS arm64; deterministic provider replies with synthetic usage
(10 input / 5 output tokens per request), manual separate fixture roles,
temporary Git projects, no inference. Models, source hashes and requirements are
fixed within each comparison. Timing varies. Exact recorded values:
[results](output-filtering-results.json).

| Case | Raw message bytes | Filtered message bytes | Calls | Synthetic tokens | Outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| Seven baseline fixtures, off | 141,557 | 141,557 | 25 | 375 | 7/7 verified |
| Same fixtures, on | 141,557 | 141,557 | 25 | 375 | 7/7 verified |
| Same fixtures, retrieval enabled | 141,556 | 141,556 | 25 | 375 | 7/7 verified; nothing omitted |
| Noisy f03, off | 16,471 | 16,471 | 3 | 45 | verified |
| Noisy f03, on | 16,471 | 15,153 | 3 | 45 | verified |
| Noisy f03, on + actual retrieval | 22,505 | 19,869 | 4 | 60 | verified |

The noisy variant explicitly adds 40 passing tests to f03; it is not the original
T24 baseline. Filtering takes about 0.25 ms across its three requests; with one
raw retrieval about 0.34 ms across four. Total task times were 1.381 / 1.374 /
1.390 seconds respectively, one trial each. No meaningful latency claim follows.
It omits 41 rows in the review payload; retrieval preserves the original.

For intuition only, bytes/4 would estimate 329.5 fewer tokens in the no-retrieval
noisy payload; that is not tokenizer measurement or provider usage. With retrieval
the transmitted payload is 3,398 bytes larger than raw baseline. Synthetic usage
is fixed per call and does not measure compression. All synthetic costs are zero.

All seven scenarios include the failed-check repair, reviewer revision and source
commit conflict checks. Interventions and failures are retained in the JSON;
no extra operator approvals resulted from filtering. The 44-test browser fixture
kept three failing tracebacks and showed the raw viewer after reload. Parser,
raw capture/cancellation/cap, reload and HTTP path/origin checks passed.
