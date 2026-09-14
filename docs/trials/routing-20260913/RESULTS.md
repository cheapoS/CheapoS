# Automatic routing trial — September 13, 2026

The single [planned attempt](PLAN.md) **failed during route selection**, before
implementation. Automatic remote selection was exercised; no worker/reviewer pair
was selected, no checks ran, and no completed commit receipt was produced.
[Sanitized machine record](attempt-1.json).

## Frozen identity and scope

- App: `019af67ac4671cf73b3f55e997359bf1ddc416e4`.
- Runtime hash: `15c11746e63781f8b96e22035faf7ed7380bd45647cbe7e3437c2ed545488836`.
- Task: `2b4ed33dc6174bbda46e06a6107cc714`.
- Source main: `4d0d29062ef65e33d3e339a1bf9653ca54228249`.
- Fixture hash: `a27155debeec3a8f94f1ad0871b85e237c28ceefbae5c13dd18d30a760b695f5`.
- Acceptance hash: `3aba67772f00a6d25a40487c7f4b8324c41644e52eb10e4a4c97329bf60df2b4`.
- Configuration/access hash: `ae4285f392604f93959081472fd98c6929e4289794542959daf99f43420f6d06`.

The easy label-normalizer fixture and its four independent tests were reused
unchanged. The operator-prepared one-item plan required the whitespace/Unicode/type
contract, a runnable README example, and unchanged passing acceptance. Its exact
check was `python3 -B -m unittest -v test_acceptance`. Preparation made no model
request. This tests execution/selection, not autonomous planning.

Measurement mode was enabled with zero paid spend, normal command authorization,
transport limits, access policy and Pause. Cumulative work/check caps did not stop
this run. The isolated profile authorized only the two exact included Kiro IDs,
plus catalog-eligible public-free routes. Global settings were untouched. A fresh
connection revision bound the grant; no prior model-quality history was copied.
Catalog membership was checked, but was not treated as inference readiness.

## Observed selection

| Route probed as worker | Access | Request time | Outcome |
| --- | --- | ---: | --- |
| `kiro/claude-sonnet-4.5` | Operator-authorized included | 2.106 s | Invalid `routing_ready` JSON arguments |
| `kiro/claude-haiku-4.5` | Operator-authorized included | 0.950 s | Invalid `routing_ready` JSON arguments |
| `openrouter/cohere/north-mini-code:free` | Public-free catalog route | 26.839 s | Provider-wide daily free-model quota exhausted |

The selector first honored the worker preference. With no completion history,
the other included Kiro route preceded public-free routes in the remaining tie
order. All three were probes, not implementation authors or worker handoffs.
The reviewer preference was retained in the contract but reviewer selection was
never reached. There was no paid/local fallback.

Both Kiro calls returned responses that failed JSON argument parsing at line 1,
column 1. They supplied no quota signal. The actual routing probe requests an
empty argument object. Earlier exporter readiness probes with a required `path`
argument passed on these models, so this result does not establish that Kiro
cannot call tools or implement this fixture. Raw probe arguments are not retained;
the evidence cannot locate the omission in the model, gateway, or transport.

OpenRouter explicitly reported its provider-wide daily free-model quota exhausted
without a reset time. The app applied that scope and skipped its remaining
eligible siblings. It paused with `routing_unavailable`; branch pause reason was
`missing_information`. No second run, unchanged Resume, or extra readiness call
was made. The observer made **zero interventions after Start**.

## Usage and qualification

Wall time was **31.604 seconds**, including **29.896 seconds** in three provider
requests; check time was zero. Accounted usage was **13,296 tokens**, including
an uncertain reservation for the failed OpenRouter request. Kiro request metrics
reported 9,874 input plus 15 output tokens in total; the remaining 3,407 accounted
tokens are not verified provider usage. Haiku reported zero output tokens despite
a returned tool envelope. The aggregate consumption output counter is also zero;
it must not replace the individual request metrics or imply no output occurred.
Retain both as recorded. Configured marginal cost was $0, not an invoice or proof
of upstream billing. There were no reviewer calls or inference during planning.

App/runtime, configuration/access, source main and both acceptance copies stayed
unchanged. The candidate still contains only the original README and tests; no
`labels.py` or runnable example exists. No acceptance command was pointlessly run
against that missing implementation. No reviewer evidence, receipt, final merge
preview, merge or push is claimed. The source and candidate diffs were clean.

Connection-scoped pool observations contain zero completion samples, independent
validations/disproofs, human integrations and activity-quality samples. These
failed probes did not become coding-quality evidence. The report's `models`
field lists observed requests, not selected providers; `selected_providers` is
null for both roles. `qualified` is false.

## Next bottleneck

The immediate product bottleneck is the automatic readiness probe, ahead of
model quality or task budgets. A small follow-up should require an explicit
marker argument and validate its exact value, keeping malformed calls rejected.
Do not broadly reinterpret missing arguments as valid JSON. Add a tiny pure
schema/parser regression, then propose one fresh easy trial with the same
fixture, access scope and preferences on a separately identified repaired app.
That would establish whether selection can proceed; it would not be a causal
quality benchmark against this failed attempt. No follow-up trial is started here.

T48 is Done as an honest controlled experiment report, not successful automatic
feature delivery. One cold-start selection failure cannot validate outcome-based
ranking, establish production success rates, or justify new default budgets.
