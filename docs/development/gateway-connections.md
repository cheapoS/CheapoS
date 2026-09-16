# Configurable gateway connections

## Implementation plan

1. Preserve the existing managed gateway contract and migrate old settings to
   OmniRoute. Add explicit OmniRoute, CLIProxyAPI, 9Router, LiteLLM and generic
   OpenAI-compatible presets; do not detect gateway identity from a port.
2. Reuse client-key storage, catalog caching, accounting, continuous sessions and
   independent-review evidence. Only OmniRoute has app-managed process startup.
3. Expose gateway selection and endpoint in Models. Keep unknown prices unknown;
   exact included-model authorization is separate from tool capability metadata.
4. Validate with deterministic catalog/transport/settings cases and the Models UI.
5. Trial CLIProxyAPI alongside OmniRoute after implementation. Use measurement
   mode, identical tasks, no prompt rewriting/compression, and record completion,
   tool calls, provenance, usage and interventions. No live inference is needed
   to configure a connection.

## Routing boundary

A gateway is an adapter, not additional quota. The same upstream account retains
its provider limits through another adapter. Existing model fallback remains
owned by cheapoS; configure gateway retries conservatively and disable hidden
paid fallbacks. Changing the active connection invalidates captured access,
never silently moves a saved run, and never copies keys to the new endpoint.

Cross-gateway automatic failover requires a task-captured set of separately
approved connections plus upstream account identity. It must not infer independent
capacity from two URLs. Qualify each adapter before enabling that policy.

## Implemented: adapter qualification foundation

Models → Startup & connection settings now selects the gateway type and its
loopback `/v1` endpoint. CLIProxyAPI, 9Router and LiteLLM use the shared
OpenAI-compatible catalog, chat and streaming transport. OmniRoute retains its
service identity check and optional owned process lifecycle. Non-OmniRoute
adapters never launch the OmniRoute executable. 9Router inference requests send
`X-9Router-Token-Saver: off` to avoid rewriting retained conversation context.

Prices absent from alternative gateway catalogs remain unknown, even when a
provider name resembles a previously free route. Operators can authorize exact
included IDs and declare missing tool metadata; explicitly unsupported tools
cannot be overridden. The existing tool probe still qualifies automatic
candidates. These declarations do not fabricate actual served model identity.

Adapter type is retained with provider configurations, including automatic and
startup selections. A saved task cannot silently follow an adapter change.
Client keys remain in memory or OS credential storage, never configuration JSON.

This release configures **one active local gateway**. It does not install the
three gateways, enroll accounts, or enable automatic cross-gateway failover.
Existing model failover works inside the selected connection. Multi-connection
routing remains the next implementation phase after the live adapter trials;
connection approval, shared-account cooldown grouping and explicit task-bound
fallback sets must land together.

## Operator trial steps

1. Start CLIProxyAPI separately with your chosen upstream account and client key.
   Keep gateway-level paid fallback and prompt transformations disabled.
2. In Models, choose CLIProxyAPI and enter its actual configured loopback API URL
   ending in `/v1`. Save the client key there if one is required.
3. Refresh models. Authorize exact included IDs if their catalog lacks prices.
   If tool metadata is absent, declare only exact IDs known to support tools.
4. Save worker/reviewer choices for Manual mode, or choose All remote for the
   existing automatic eligible-model selection. Use a new disposable task.
5. Run a small edit/check/review task with measurement mode enabled and the chosen
   free/included spending policy. Record actual model identity, all usage,
   tool-call errors, response latency, recovery and interventions.
6. Repeat with OmniRoute on the same task. Repeat for other adapters only if
   they add useful provider access or solve a demonstrated connection failure.

## Validation

Seven new network-free cases took 0.005 seconds together. They cover default
migration, external lifecycle, unknown prices, credential/access revocation,
operator capability declarations, adapter pinning, and 9Router transport
(history, usage and no hidden retry). Existing gateway, credential, access,
startup, routing, streaming, identity and readiness cases were also exercised.

Disposable browser verification: select CLIProxyAPI, save a new loopback URL,
observe its catalog and gateway name, select model IDs for worker/reviewer, and
save successfully. Uses fake catalog metadata only; no inference, personal data,
or real credentials. Live provider qualification is intentionally still pending.
