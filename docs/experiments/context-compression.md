# Context compression evaluation

**Decision: defer an additional runtime layer.** The installed gateway's
SmartCrusher pass changed none of 28 real fixture request payloads. A synthetic
JSON table compressed, but blindly applying the pass also changed protected
user-request and JSON-source bytes. No proxy, library or default was added.

## Candidate and compatibility, inspected 2026-09-13

The single candidate was OmniRoute's existing **Headroom SmartCrusher** with
`minRows=8`. This was the smallest offline experiment because its code and
dependencies were already installed. It scans non-system/developer message text
for object arrays or JSON fences and chooses a smaller GCF/TOON representation.
It is not the standalone Headroom Python library.

Installed package: OmniRoute **3.8.49**, MIT; Node **26.3.0**, inside its declared
supported range; bundled `@toon-format/toon` **4.1.1**, MIT. No package was
installed or upgraded. The probe copies only the installed compression source
to a temporary directory to run TypeScript outside node_modules, resolves the
already installed TOON dependency, and removes temporary payloads afterward.
[Recorded source hashes and versions](context-compression-results.json) identify
the exact nine source files. The probe is not imported by cheapoS.

Read-only SQLite inspection selected only these five keys from the installed
gateway's `key_value` compression namespace:

| Setting | Stored value |
| --- | --- |
| enabled | false |
| defaultMode | off |
| preserveSystemPrompt | true |
| autoTriggerTokens | 0 |
| cacheMinutes | 5 |

No credentials, prompts, provider configurations or call logs were queried.
These are stored global settings, not proof about every running connection or
per-request override. No settings were changed or gateway process launched.
The installed generated CLI advertises GET `/api/settings/compression`; the
local schema migration documents the same namespace. File/DB inspection avoided
assuming a particular live endpoint or authentication state.

The check-in's [OmniRoute compression engines](https://github.com/diegosouzapw/OmniRoute/blob/release/v3.8.51/docs/compression/COMPRESSION_ENGINES.md)
and [RTK guide](https://github.com/diegosouzapw/OmniRoute/blob/release/v3.8.51/docs/compression/RTK_COMPRESSION.md)
were rechecked, but describe 3.8.51, so installed 3.8.49 source controlled this
experiment. The currently published [standalone Headroom](https://github.com/headroomlabs-ai/headroom)
offers a separate library/proxy/MCP approach; it was not installed or treated as
an equivalent engine. [Caveman](https://github.com/JuliusBrussee/caveman) includes
telemetry controls and would require a separate integration decision.
[Ponytail](https://github.com/DietrichGebert/ponytail) is principally an
implementation-discipline layer, already addressed by T22. Neither was selected
as a second candidate. Their marketing results are not cheapoS measurements.

## Reproduction

Requires the existing gateway package and a Node version supporting TypeScript
stripping. It uses no model credentials, network inference or external installs:

```sh
python3 -B scripts/context_compression_benchmark.py \
  --gateway-package /opt/homebrew/lib/node_modules/omniroute \
  --output /tmp/context-compression-results.json
```

The Python harness reruns all seven deterministic T24 controller scenarios, plus
the explicitly separate noisy f03 variant from T26. A temporary observer captures
original and optionally filtered messages at the request boundary. It does not
modify tool schemas or arguments. The offline Node harness then applies exactly
one installed SmartCrusher pass to each captured stage. It asserts byte-equivalent
message structure for every fixture request. No altered payload is executed.

The same pinned fixture hashes and model settings are used within each comparison.
The existing T21 brief/continuation and T22 concise policy are present in all arms;
the raw arm means raw check output, not reverting those completed cards.

| Captured stage | Requests | Before bytes | After added pass | Changed requests | Pass overhead |
| --- | ---: | ---: | ---: | ---: | ---: |
| Existing concise context + raw checks | 28 | 157,380 | 157,380 | 0 | 0.172 ms |
| Existing concise context + T26 filtering | 28 | 156,062 | 156,062 | 0 | 0.027 ms |

These measure serialized message bytes, excluding tool schemas and transport
framing; timing is one local trial with warmup effects. All eight controller
scenarios passed before offline replay. Because all replay payloads are equal,
the extra pass has no fixture benefit and changes no request/cache prefix.
It required zero retrieval calls on these fixtures. No real provider token,
latency, billing or model-quality improvement was measured.

## Fidelity and retrieval stress case

A separate 40-row synthetic object array shrank from **3,901 to 1,557 bytes**.
Decoding produced deep-equal JSON, and one local hash-keyed retrieval recovered
the exact original 3,901 bytes. Compression plus assertions/roundtrip took
3.077 ms. If the original were requested as extra context, compressed plus
retrieved content would be 5,458 bytes before framing: greater than baseline.
This is not an end-to-end model trial.

System/developer text and assistant tool-call arguments stayed unchanged.
However, sending that same JSON as a user request or source-tool content changed
its byte representation. Semantic roundtrip alone does not satisfy cheapoS's
contract to preserve exact requests/code evidence. A production integration would
need explicit controller-owned eligibility, durable original retrieval, and
stable schema/cache behavior. The installed reconstruction helper is an offline
oracle, not an automatically exposed cheapoS retrieval tool.

Therefore the broad pass fails the protected-input adoption gate, and the bounded
eligible fixture data shows no useful reduction. The negative result completes
T27. Direct-local behavior remains independent of the gateway. T26 raw retrieval
and its optional filter remain available without this layer.

## Remaining unknowns and adoption gate

A later experiment needs an operator-selected real model pair and budget, repeated
trials with failures reported, larger representative repositories, cache-token
accounting, and durable retrieval integration before any runtime adoption.
No user requirement, exact replacement, file version, verification identity,
review failure or tool schema may be removed to improve the result.
Provider/gateway/context integration is covered by the final full test gate;
the offline probe's fidelity assertions and eight fixture outcomes passed.
