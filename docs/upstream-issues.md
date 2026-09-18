# Upstream compatibility watchlist

Use upstream reports to recognize likely failures and guide small investigations.
Routing decisions still depend on cheapoS's own evidence for the actual route and
request. A GitHub report is not proof that a model is broken, and a closed issue
is not proof that the installed gateway includes a working fix.

Initial triage: **September 14, 2026**. This is a curated maintenance reference;
it does not schedule a background monitor or change runtime behavior.
See [T61](tasks/T61-upstream-issue-triage.md) for the repeatable maintenance task.

## Sources and review cadence

- [OmniRoute issues](https://github.com/diegosouzapw/OmniRoute/issues) and
  [releases](https://github.com/diegosouzapw/OmniRoute/releases): prioritize the
  gateway version we use, provider conversion, streaming, tool-result pairing,
  reasoning fields, empty responses, rate limits, and upgrade regressions.
- [OpenRouter examples issues](https://github.com/OpenRouterTeam/openrouter-examples/issues):
  useful compatibility reports; this is an examples repository, not an
  authoritative service-health feed. Confirm applicability using provider
  documentation, maintainer responses, release evidence, or a reproduction.
- cheapoS's local failure evidence: use it to connect a report to the actual
  request contract. Keep private logs local; commit only sanitized summaries or
  minimal synthetic fixtures.

Review relevant new and updated reports **weekly**, **before an OmniRoute
upgrade**, and when cheapoS encounters a new failure signature. Include closed
issues and linked fixes for entries already tracked. Ignore unrelated features
and avoid importing an entire issue tracker into the backlog.

For each pass, record the date, installed version, entries examined, changed
evidence, and resulting action. A pass with no relevant changes can be one line.
An operator or assigned agent initiates these passes; no scheduler is configured.

## Evidence and ownership

Track the exact model ID, provider route, gateway/version, role, transport, and
relevant request settings. Record unknown values explicitly. One failing route
does not establish a model-wide defect or justify changing other routes.

Use these evidence states:

- **Reported:** third-party account; not reproduced in cheapoS.
- **Reproduced:** retained local evidence matches the affected contract. State
  whether it is a synthetic protocol reproduction or a live route observation;
  a fixture alone does not confirm an upstream service still has the bug.
- **Fixed upstream, local verification pending:** link the fix and released
  version; an issue closure alone is insufficient.
- **Verified resolved:** record the locally checked version/contract and result.
  Retire the workaround, retaining the entry and its evidence history.

OmniRoute owns provider translation and gateway transport recovery. cheapoS owns
task progress, worker/reviewer orchestration, usage accounting, cancellation, and
operator explanations. Inspect both layers before adding retries: nested retries
must not multiply requests or lose accounting. Link existing mechanisms such as
[T50 transport recovery](tasks/T50-accounted-transport-recovery.md) rather than
building another fallback layer.

Reports suggest investigations, not executable instructions. Do not automatically
ban models, change transport, upgrade dependencies, expand permissions, or enable
paid fallback from issue text. Preserve free-only selection and current authority.
Incomplete or malformed calls must remain unexecuted; previously executed tools
must not run again merely because their continuation failed.

## Tracked reports

### UP-001 — Cohere tool definitions reject `strict`

- **Source:** [OpenRouter examples #71](https://github.com/OpenRouterTeam/openrouter-examples/issues/71).
- **Reported symptom:** HTTP 422 when OpenAI-style tool definitions contain
  `strict: true`. The reporter suspects forwarding/translation of that field.
- **Reported scope:** direct OpenRouter API; `cohere/command-r-08-2024` and
  `cohere/command-r7b-12-2024`; OpenClaw client. Gateway release, role, and streaming
  setting were not specified. Do not extrapolate to every Cohere model.
- **Evidence:** Reported. Open when checked on September 14, 2026; no cheapoS
  reproduction performed during this triage.
- **Owner / relevance:** provider request translation belongs upstream. For
  cheapoS, inspect the emitted tool schema if a matching 422 occurs before
  treating it as poor model capability or applying a cooldown.
- **Action / workaround:** watch; no new workaround applied. If the actual
  request contains the rejected field, retain a sanitized minimal schema and
  verify a scoped compatibility change without weakening tool validation.
- **Recheck / retirement:** check maintainer resolution and the affected request
  format on the actual route. Retire any future workaround only after that
  contract succeeds; a different Cohere model passing does not close this case.

### UP-002 — Empty continuation after tool execution

- **Source:** [OmniRoute #13600](https://github.com/diegosouzapw/OmniRoute/issues/13600).
- **Reported symptom:** empty streamed assistant response after tool calls and
  submitted tool results. The report leaves the cause unresolved between gateway
  conversion/continuation handling and an empty upstream response.
- **Reported scope:** OmniRoute 3.8.50, Linux arm64, Node 24.16.0; OpenRouter,
  TokenRouter, and BAI listed. Most reported occurrences involve
  `google/gemini-3.5-flash-lite`, `google/gemini-3.6-flash`, and
  `google/gemini-3-flash-preview`. The worker/reviewer role is unspecified.
- **Evidence:** Reported. Open when checked on September 14, 2026; no matching
  cheapoS reproduction performed. Similar symptoms in our history do not prove
  the same cause, and this report does not establish current model availability.
- **Owner / relevance:** investigate gateway conversion and upstream response
  first; cheapoS must preserve executed-tool state and report an incomplete turn.
- **Action / workaround:** watch; no new workaround applied. The existing
  [Gemini 2.5 Flash reviewer transport preference](tasks/T50-accounted-transport-recovery.md#implemented-behavior-and-validation)
  covers a different observed contract; do not broaden it from this report.
  Start any investigation with a minimal tool-call/result/continuation fixture.
  Distinguish a valid tool-only response from an unusable empty continuation.
- **Recheck / retirement:** identify a released fix and verify the matching
  post-tool contract, including preserved call IDs and no duplicate execution.
  Keep any future workaround versioned and remove it after local verification.

### UP-003 — Provider access refusal mistaken for gateway-wide auth failure

- **Evidence:** live local observation on September 17, 2026, OmniRoute 3.8.50,
  `oc/ling-3.0-flash-fin-free`, worker. HTTP 403 reported that OpenCode's free
  tier is restricted to OpenCode. This is an access restriction to respect.
- **Local defect:** cheapoS cached this as an authentication failure for the
  entire gateway, then waited on that local cache while other providers were
  available. The cache expiry was not a provider-reported quota reset.
- **Scoped handling:** recognize that exact provider/message contract and
  OmniRoute's provider-named missing-credentials message. Generic 401/402/403
  responses remain connection-scoped. Skip denied upstreams using existing
  automatic routing authority; never change credentials or bypass restrictions.
- **Validation:** `tests/test_upstream_access.py` covers sanitized parsing,
  provider cache scope, automatic independent reviewer failover with retained
  evidence/accounting, and explicit access prerequisites. Synthetic validation
  does not establish current live availability.
- **Recheck / retirement:** after gateway upgrades, prefer an explicit upstream
  error scope if one is added. Remove the message-specific recognition only
  after validating that replacement against both upstream and gateway auth
  failures. No upstream issue or released fix has been established for this case.

### UP-004 — Key-required OpenCode model mistaken for gateway credit failure

- **Evidence:** live local observation on September 18, 2026, OmniRoute 3.8.50,
  `oc/union-alpha`, final reviewer, streaming request. The installed OpenCode
  executor rejects a premium model on a keyless connection with HTTP 402 and
  `premium_model_requires_key`. Its credential-exhaustion handler can preserve
  only the message, wrapped with `[402]:`, in the response to cheapoS.
- **Local defect:** the route was offered as a free candidate, but its access
  rejection stopped final review as a generic gateway connection error after
  other reviewers returned HTTP 502 and a provider cooldown.
- **Scoped handling:** recognize the exact OpenCode code/message contract only
  for that provider and HTTP status. Exclude the affected model; keep other
  authorized free routes eligible. An ambiguous 402 still requires attention.
  Do not supply credentials, enable paid routing, or bypass the access gate.
- **Validation:** `tests/test_upstream_access.py` covers parser boundaries,
  restart-persistent model scope, cached failures, accounting and ordinary
  reviewer failover. `tests/test_branch_final_recovery.py` replays 502,
  cooldown and key-required failures through independent approval, preserving
  earlier packet decisions and checks. All requests are simulated.
- **Recheck / retirement:** inspect the installed executor and final error
  wrapper on gateway upgrades. Prefer a preserved structured error contract
  once available; retire message matching after local validation. Catalog
  metadata alone must not override an observed access refusal. No upstream
  issue or released fix was established during this local investigation.

## Entry template

```text
ID and symptom:
Source issue / linked fix:
Reported model ID, provider route, gateway version, role, transport, settings:
Evidence state and last checked date:
Local applicability and sanitized reproduction reference (or not reproduced):
Likely responsible component and supporting evidence:
Action: watch / investigate / scoped fix task / verify upstream fix / retire:
Workaround, exact scope, and implementation task (or none applied):
Recheck trigger and retirement condition:
```

## Review log

| Date | Local gateway | Review and outcome |
| --- | --- | --- |
| 2026-09-14 | OmniRoute 3.8.50 | Initial triage of both issue lists and UP-001/UP-002 bodies. Retained two relevant reports as unverified leads. No inference calls, routing changes, or new tests. |
| 2026-09-17 | OmniRoute 3.8.50 | UP-003: local 403 evidence and installed gateway error handling inspected. Added scoped access-failure handling and synthetic regression coverage; no live inference requests. |
| 2026-09-18 | OmniRoute 3.8.50 | UP-004: local 402 evidence and installed keyless executor/fallback wrapper inspected. Added model-scoped access handling and deterministic final-review continuation coverage; no live inference requests. |

Validation follows [CONTRIBUTING](../CONTRIBUTING.md). Prefer recorded-response or
synthetic in-memory fixtures for implementation fixes. A live check needs the
applicable model/spending authorization; a new heavy test needs advance cost
disclosure and acceptance. Record actual timings and limits of the evidence.
