# Signed Club request health

The optional Club sync places `request_health` inside each signed usage event.
Only post-consent, non-synthetic, dispatched requests with reconciled, complete
token usage are eligible. Reservations and incomplete usage stay local. Request
IDs retain their existing stable event identities; changed facts update that
same event, and a lost acknowledgment reuses the exact saved signed envelope.

The journal records the configured gateway and routing namespace before dispatch.
For OmniRoute, `antigravity/anthropic/model` means gateway `omniroute`, route
`antigravity`, and the separately recorded model identity. The catalog's
`owned_by` field and a model family do not establish a provider. New route names
work without a model catalog update. `oc`/`kr` aliases normalize to `opencode`/
`kiro`; unqualified or opaque routes remain unknown. Direct compatible endpoints
without authoritative route metadata also remain unknown. URLs, keys, prompts,
source, custom connection names and raw error messages are never included.

`request_health.version = 1` reports an outcome, optional measured duration,
optional bounded failure category, and whether the request was marked recovery.
Gateway/provider fields and model names require model-sharing consent. Access
class comes from explicit accounting evidence, never a model-name guess.

Duration is the full app request attempt, including local preparation and waits;
it is not time to first token or upstream-only latency. Means use duration sum /
measured duration count, including failed/cancelled attempts and measured zeroes.
Missing measurements stay unknown. Response success is distinct from task or
independent-review success.

## Coordinated rollout

Deploy the Club signed-health migration and endpoint from cheapskate-club PR #2
before enabling this client version's reporting. Older Club servers ignore these
new fields; they cannot publish the new measurements. Existing accepted events
are amended by the normal fingerprint/reconciliation mechanism after upgrade;
unknown historical routing evidence is not guessed.

For legacy requests that lack dispatch-time route fields, normal journal ingest
can recover routing from the saved dispatch scope. Its endpoint, connection
revision, requested model and role must match exactly, and the captured connection
must explicitly be OmniRoute. Ambiguous, changed or missing connections are not
used. The requested namespace establishes the route even when the served model
omits that namespace. Explicit local access evidence also establishes a local
route. Existing explicit route fields, including unknown values, are preserved.
No current connection settings or model/vendor dictionary is consulted.

This runs during the existing saved-task ingest on restart/save. It retains
request IDs and token totals and never edits task records. Recovered route facts
are sent as signed corrections under the same event IDs and existing consent;
the site changes only after accepting them. Requests without retained evidence
remain unknown. Endpoints and connection revisions stay local.

The Club publishes metrics derived from accepted event rows joined to ingestion
receipts. Legacy client aggregate snapshots are not sufficient proof of request
membership. Completion/model-pair/stage claims need their own validated receipts.

## Coverage limit

This version describes the **reconciled signed usage sample**, not every attempted
provider call. In particular, a 429 or connection failure with no token usage may
remain excluded. Do not market this sample as provider uptime or a complete error
rate. A future signed attempt ledger can include failed calls without inventing
zero token usage; it should remain separate from billable usage accounting.

Validation: focused Club, journal, metrics, lifetime integration and startup tests;
no live model calls, service restarts or historical data edits.
