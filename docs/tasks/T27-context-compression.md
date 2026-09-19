# T27 — Evaluate one optional context-compression layer

**Depends on:** T21, T22, T26. **Size:** M. **Result:** an evidence-based adopt/defer decision for context compression, with an optional bounded prototype if justified.

## Read first

T21 brief/continuation contracts, T22 exact-edit handling, T26 filtering metrics, existing gateway adapter boundary, and Headroom/Caveman/Ponytail/OmniRoute source links in the check-in. Recheck current upstream/version compatibility before choosing an integration.

## Scope

This is a research-and-prototype card, not permission to turn on several proxies or install everything in the video. The useful concise-output and minimal-code principles are already addressed in T22; terminal-output filtering is T26.

## Implementation

1. Inspect the installed gateway's actual compression capabilities and current configuration through supported read-only APIs/files. Do not assume a Headroom-named gateway feature is the standalone Headroom library. Do not print credential configuration.
2. Choose one candidate: an existing supported gateway pass, or an optional Headroom-style library/adapter in a temporary prototype. Document why it is the smallest useful experiment. If an additional dependency is needed, identify exact package/version/license/runtime and obtain the normal explicit installation choice; do not make it a default app requirement.
3. Compress only appropriate input context. Preserve original requests, exact code/edit evidence, tool schemas/JSON, file versions, and required review failures. Provide a local retrieval path for omitted material. Inability to retrieve needed evidence is a failed experiment.
4. Keep prompt/cache behavior stable where possible. Measure compression overhead and retrieval calls, not just initial payload reduction. Ensure direct-local operation still works without the optional layer.
5. Compare baseline, existing concise/filter behavior, and the single added context pass on the same fixture set/model settings. Repeat real-model trials only with explicit operator model/budget selection. Report small sample limitations and all task failures.
6. Write `docs/experiments/context-compression.md` with method, exact versions/settings, results, decision, and remaining unknowns. If adopting a prototype, isolate it behind a disabled-by-default capability/config switch with a straightforward off path. If deferring, a clear negative result is a successful completion of this card.

## Acceptance

An independent reader can reproduce the experiment. Original evidence is retrievable; no malformed edit/review is executed or accepted after compression. The report distinguishes estimated and provider-reported usage and does not add overlapping savings percentages. No new default telemetry, compulsory proxy, or installed dependency is left unexplained.

## Validation / limits

Run relevant provider/gateway/context tests and T24/T26 comparison scenarios. Never use an unavailable real-model benchmark as proof of token savings. Do not enable default compression based on marketing percentages or drop user requirements to improve the score. Adoption is conditional on preserved correctness and a measured useful result.

## Completion record

Status: Done

- Behavior delivered: [Reproducible offline evaluation](../experiments/context-compression.md) of the already installed gateway SmartCrusher pass; explicit defer decision, no runtime integration or dependency installation.
- Acceptance evidence: 28 captured request payloads unchanged across raw/filtered stages; eight controller scenarios passed. Synthetic roundtrip/retrieval passed, but broad pass changes protected user/source bytes, so adoption gate fails.
- Commands and results: context_compression_benchmark.py with installed OmniRoute 3.8.49 and Node 26.3.0: PASS, decision defer. Exact hashes/settings/results recorded; no live inference. Final integration gate recorded separately.
- Browser scenarios and results: No runtime UI added; T26 raw-evidence viewer already verified.
- Remaining limitations: No real-model quality/token/billing claim; no production retrieval integration for this candidate. A future adoption experiment needs explicit model/budget selection and repeated representative trials.

Before implementing, read [TASKS.md](../archive/TASKS.md) for the shared contract. Update this record and the matching board row when complete.
