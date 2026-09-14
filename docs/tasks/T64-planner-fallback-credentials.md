# T64 — Preserve credentials when planning falls back to another role

Status: Complete
Priority: P1 — authenticated planning
Depends on: T62
Size: S
Planning baseline: `db774c7`, September 14, 2026

## Outcome and reproduced failure

Using the reviewer as planner must use that reviewer's authorized connection
and credentials while recording the request as planning work.

`Engine.configure` stores a UI-entered direct-provider key under
`(reviewer, base_url)`. `_resolve_provider_config` returns the reviewer config,
but dispatch calls `provider_key('planner', config)`. A synthetic direct HTTPS
provider reproduced a nonempty reviewer key and an empty planner key. Shared
OmniRoute keys and reviewer environment variables can mask this failure.

## Read first

[engine.py](../../cheapos/engine.py) (`configure`, `provider_key`,
`_resolve_provider_config`, `_perform_request`),
[providers.py](../../cheapos/providers.py), and
[gateways.py](../../cheapos/gateways.py).

## Implementation work

1. Resolve provider configuration together with its credential source. Preserve
   a distinction between the request's role (`planner`) and the source role
   whose provider/credentials were deliberately inherited.
2. An explicit planner uses planner credentials; reviewer fallback uses that
   reviewer's credentials; any retained legacy worker fallback uses its own.
   Never try arbitrary other-role keys merely because authentication failed.
3. Keep credentials bound to the resolved endpoint and the saved task/provider
   policy. Changes to global settings must not silently move an existing task
   to a new provider or leak the former provider's key to a different host.
4. Preserve the existing environment-variable and OmniRoute credential flows.
   Reuse current secret-storage policy; this task does not add direct-key disk
   persistence. Store only non-secret provenance if a reference is needed.
5. Configuration output, task JSON, request metrics, logs, and errors must never
   contain key values. Retry/model-discovery paths must use the same resolver.

## Acceptance and focused validation

- A synthetic UI-configured direct reviewer key reaches the fallback planner's
  provider constructor. Usage and request metrics still say `planner`.
- Explicit planner credentials win when configured; environment-based and
  shared OmniRoute authentication continue to work.
- Endpoint changes and missing credentials do not borrow unrelated keys.
- Use temporary Engine configuration, synthetic key strings, environment patches,
  and captured provider constructor arguments. No HTTP service or inference is
  needed to establish credential identity. Report added-case timings.

## Completion record

Completed in the T64 scoped commit. Provider resolution retains a non-secret
credential_role and pins fallback to saved reviewer/worker settings. Endpoint-bound
keys and environment/shared-gateway flows are preserved; global planner changes
cannot replace a saved fallback. Two deterministic tests passed in 0.007s.

Captured gateway constructor verification now covers reviewer-key planning dispatch and retries with planner metrics, without secret leakage: 8 existing transport cases passed in 0.004s; new case under 0.001s.
