# Expanded routing qualification — September 13, 2026

**The one automatic task completed and passed independent qualification.**
cheapoS wrote the implementation and README, ran the unchanged supplied tests,
obtained review, and committed the result without intervention after Start.
T44 remains deferred; this was the small label-normalizer fixture, not the exporter.

[Predeclared plan](PLAN.md) · [Diagnostic record](diagnostic.json) ·
[Execution record](attempt-1.json) · [Independent evidence](independent-qualification.json).
The earlier failed [automatic attempt](../routing-20260913/RESULTS.md) and
[exporter attempts](../exporter-20260913/RESULTS.md) remain unchanged.

## Identity and path

Frozen app: `e06e98d175de0db601f8c1c16af328b0f9ce6d14`.
Task: `0b7be4142fc342b296004c7bfd90925d`.
Runtime hash: `f8308e194927cb69c13ff43dcdd1718c908aa5a02c40729d1e54202d69dc5ec1`.
Fixture hash: `a27155debeec3a8f94f1ad0871b85e237c28ceefbae5c13dd18d30a760b695f5`.
Acceptance hash: `3aba67772f00a6d25a40487c7f4b8324c41644e52eb10e4a4c97329bf60df2b4`.
Configuration/access hash: `0ce6558cab3ff1d4ede9e6ae8f4e064ff7fbc50339c6be0110ff8fc066d762fa`.

The isolated profile allowed the two explicitly included Kiro routes and eligible
public-free routes, with zero paid spend. The task used automatic remote selection,
retaining role preferences rather than injecting providers after preparation.
No previous completion history was copied. This does not qualify quality-based
ranking against competing proven candidates; it qualifies the observed selection
and execution path. Planning was operator-prepared, not model-generated.

| Role | Requested route | Gateway-reported served model |
| --- | --- | --- |
| Worker | `kiro/claude-sonnet-4.5` | `claude-sonnet-4.5` |
| Reviewer | `kiro/claude-haiku-4.5` | `claude-haiku-4.5` |

Both targeted diagnostics used the real cheapoS gateway adapter, request
serialization, streaming parser and tool validation with the exact required marker.
No returned tool was executed. Each route passed once; both automatic selections
then reused matching fresh cached observations, with **zero execution probes**.
The gateway exposed the distinct served model fields above in diagnostics and work
requests. These are response metadata, not independent upstream identity attestation.
Application diagnostic fallback was disabled; OmniRoute's internal fallback control
and attempt chain were unavailable. Therefore these are configured-route diagnostics,
not claimed qualified pinned-model tests. No gateway attempts were invented.

The eligible Kiro preferences succeeded, so OpenRouter was not contacted. The
operator's balance top-up was not treated as verified remaining quota or paid-model
authorization. No account was deliberately exhausted or inspected outside OmniRoute.

## Usage and result

| Phase | Requests | Accounted/reported tokens | Wall time |
| --- | ---: | ---: | ---: |
| Targeted diagnostics | 2 | 9,553 reported | 3.431 s |
| Automatic execution | 10 (5 worker, 5 reviewer) | 85,138 accounted | 53.325 s |
| Combined | 12 | 94,691 | 56.756 s of measured phase time |

Automatic execution spent 44.349 seconds in provider requests. The two required
check executions took 0.12 and 0.11 seconds. No inference errors, handoffs, Resume,
or operator interventions after Start occurred. Measurement mode retained normal
monetary/access/command and transport safeguards; cumulative arbitrary work caps
did not censor this run. Configured cost was $0 under included access, not a billing
receipt. Provider output-token reporting included zeros despite returned tool calls;
retain reported counts rather than inferring actual zero output. The combined
phase time excludes the operator's interval between phases.

The unchanged four acceptance methods passed for the actual candidate. Independent
inspection verified string type rejection and Unicode-preserving whitespace
normalization. The README's complete Python example ran separately and produced
exactly the expected three lines in 0.0011 seconds. No source or test edits were
made by the observer. The retained independent artifact SHA256 is
`f2d03be44243e652205afb903a4722e628b4e117953a440cf4a84ced8577662b`.

Completed feature commit: `ec05b3f3b98cdf7af8cde54bc4073eea3af0587c`.
Parent: `a02c78a61b1f7b162b6c5a02b43a991519c802d2`.
Tree: `834195ba7ceb0b073c66024cfebffc6503072209`.
The receipt matches the run/item and the actual commit object/parent/tree. A fresh
controller preview reported merge available. Source main, app/runtime, configuration
and source/candidate acceptance remained unchanged. **No merge or push occurred.**

The existing pool recorded one completed receipt per role. After independent
qualification, the trusted local adjudication hook recorded one independently
validated result per role, keyed to that retained artifact. There are zero human
integrations. This observer annotation happened after the run, not as coaching;
no task execution or model request was resumed.

## Trace finding and follow-up repair

The frozen run correctly retained request order, selected routes, reported identities
and cached-observation events. Its large discovery catalog filled the bounded
candidate list before the cached-probe detail rows. The list was marked truncated,
but the UI initially hid that fact and displayed only 40 of 64 retained rows.

After the run ended, a separate repair prioritizes probe actions within the bounded
candidate list and displays all retained rows with explicit partial-evidence notices.
The saved trial evidence was not rewritten to pretend those missing candidate rows
were retained. Cached reuse is demonstrated by the original routing events and zero
probe requests. Three pure trace tests pass in 0.001 seconds; 75 focused Node checks
pass in 86ms. These presentation/retention changes were not the live frozen runtime.
Browser verification remains pending after the earlier documented client block;
Node markup checks are not presented as a browser pass.

T46–T48's expanded implementation and this qualification are recorded. The explicit
marker passed where the earlier empty-argument probe failed, and this attempt
completed. Changes to the runtime and preparation mean this is not a controlled
causal comparison or a production success-rate estimate. T44 can be attempted
again through cheapoS when the operator returns to it. No additional trial or new
budget default follows automatically from this one success.
