# Free routing and spending authorization

September 14, 2026. Design recommendation; the follow-ups below are **not implemented** and do not authorize account changes, paid requests, or local fallback.

## Keep the single gateway; make spending permission separate

cheapoS now sends remote model requests through the configured local OmniRoute connection. Direct installed Ollama remains available. That controls the destination of requests, not the cost of the upstream model selected there.

The next engine feature should be a durable spending policy independent of execution mode, model placement, and Interactive/Unattended supervision. Selecting Manual, adding a stronger planner, retrying, or resuming must not turn free-only permission into permission to spend.

Current automatic remote eligibility includes both public-free models and operator-declared included access. The latter can have a zero marginal estimate despite paid catalog pricing. The cumulative one-cent cutoff applies to automatic remote/delegate work within the task budget; Manual uses its task budget. These are current accounting controls, not a provider-side promise of zero billing. See [access classification](../../cheapos/access_policy.py) and [execution behavior](../EXECUTION.md).

**Incident attribution is still under investigation.** The operator suspects a supervising Gemini agent made requests outside cheapoS while debugging a run. Current Manual settings alone do not establish who authorized or dispatched a billed request. Compare provider billing timestamps/models with cheapoS request records and OmniRoute request traces. An unmatched charge can indicate another client, gateway-internal retries, or missing accounting evidence; absence from one log is not proof. Requests made by another client are outside cheapoS's engine budget even when they use the same gateway. Provider-key isolation and upstream limits address that separate path.

## Provider controls worth keeping

Use a dedicated OpenRouter inference key only inside OmniRoute and a separate OmniRoute client key for cheapoS. The upstream key should have the operator's explicit cap; no automatic budget renewal unless requested. Follow [the setup guide](../USER_GUIDE.md#protect-the-credits-you-keep). A positive allowance is a damage limit, not free-only authorization, and a management key should not be given to a coding worker.

OpenRouter also documents `provider.max_price`: prompt/completion ceilings are in dollars per million tokens, with additional request/image price fields. Unlike a preference for cheaper providers, a price ceiling can reject requests when no provider qualifies. This is promising for zero-price routing, but cheapoS does not currently send that constraint. We have not verified that OmniRoute preserves it through translation, model mappings, retries, and every fallback. Do not advertise it as active protection yet. [OpenRouter provider selection](https://openrouter.ai/docs/guides/routing/provider-selection)

## Why a combo called `free` is not the next default

OmniRoute documents priority and fill-first combos. Their ordering controls do not establish that every member is free, covered by the operator's account, suitable for tools, or available. Specific provider/model lists in the pasted recommendation are examples to discover and validate, not an installation guarantee. [OmniRoute combo documentation](https://github.com/diegosouzapw/OmniRoute/blob/release/v3.8.50/skills/omni-combos-routing/SKILL.md)

OpenRouter's `openrouter/free` is documented as selecting a random eligible free model per request and reporting the selected model in the response. That supports convenient chat experiments, but using it for both roles can select the same worker and reviewer. Its model count changes; don't hard-code the quoted “25.” OmniRoute's exposed ID must come from its catalog rather than guessing provider prefixes. [OpenRouter free router](https://openrouter.ai/docs/guides/routing/routers/free-router)

Keep the current named candidates for coding and independent review. Before accepting an opaque combo, establish its actual members and spending constraints, preserve served-model identity, and reject same-model or unknown-identity independent reviews. An arbitrary combo name must not be treated as a concrete model merely because it lacks the word `auto`. Existing [served identity checks](../../cheapos/served_identity.py) and combo exclusions are foundations to extend, not remove.

Local fallback also needs a separate choice. Exhausted cloud quota should not silently launch a large Gemma workload on a laptop. Public-free service and subscription/included access should remain visibly distinct.

## Proposed implementation order

1. **Spending authorization across every mode and role.** Capture the operator's policy before planning, then enforce it for coordinator, planner, worker, reviewer, probes, repairs, and fallbacks. Models and task text cannot grant or widen it. Preserve the policy and usage on restart/resume. Keep the requested one-cent reporting tolerance explicit and separate from authorization to select paid models; don't silently remove or increase it.
2. **Verified upstream enforcement.** Establish the deployed OmniRoute contract for passing price constraints and applying key/model restrictions. Use deterministic fixtures to verify that paid, unknown-price, mapped, and fallback targets cannot escape the chosen policy. Surface which restrictions are verified and which are only estimates. Any live qualification needs a separately authorized model/spend policy; this document grants none.
3. **A simple Automatic UI over eligible named routes.** Hide provider complexity while showing the selected model and each handoff in Details. Enable a transparent combo only after membership, billing restrictions, and served identity are verified. Offer local fallback and paid fallback separately; neither is implicit when free service is unavailable.

Use small deterministic regression cases and existing integration coverage. Propose any new heavy/live workflow with its cost before adding it. No routing, key limits, included-model grants, or spending settings were changed while writing this assessment.
