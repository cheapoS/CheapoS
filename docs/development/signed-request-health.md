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

The Club service must support signed request-health ingestion and publication
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

### Metadata backfill after reconnecting

Reconnects can leave accepted historical events outside the current connection's
local `sent` map. Normal usage sync must continue excluding the pre-consent
baseline. `club_routes.backfill_routes` uses a separate metadata path instead:

1. A signed `route_history` lookup sends at most 500 opaque event IDs, with no
   models, routes, tokens or task details. The Club returns only IDs already
   accepted for this installation and current owner, linked to usage receipts.
2. A signed, sequenced `sync` with `events: []` and up to 100 `route_corrections`
   sends only `{event_id, gateway, provider}` for confirmed IDs. The Club rejects
   missing, foreign or unreceipted events and all accounting fields. It never
   inserts usage or changes model names, tokens, categories, health or outcomes.
3. The site publishes receipt-backed `model_routes` for labels separately from
   the existing health sample. A provider name therefore does not manufacture
   reliability, latency, recovery or task measurements.

The existing installation key, active pairing, sharing and model-sharing consent
apply. Turning model sharing off clears metadata; negative lookups never upload
private history. The independent processed map is scoped to the pairing/account
and is cleared on model-consent changes. It never changes `baseline` or `sent`.
Lost acknowledgments retain the exact signed envelope for replay. Unknown routes
are not inferred from model prefixes. Each normal sync tick can process one
metadata batch; discovery failures retry later without blocking normal usage.

The Club service must support signed route-history lookup and metadata corrections
before this client can backfill records. Service deployment is coordinated
separately. The existing app restart/save ingest recovers locally
retained connection evidence; the background Club sync performs the backfill.
It needs no new model calls. Older servers cannot provide the lookup and receive
no metadata mutation. Inspect `route_backfill_error` in local connection state
when diagnosing an incomplete rollout; do not clear the sharing baseline.

This runs during the existing saved-task ingest on restart/save. It retains
request IDs and token totals and never edits task records. Recovered route facts
are sent as signed corrections under the same event IDs and existing consent;
the site changes only after accepting them. Requests without retained evidence
remain unknown. Endpoints and connection revisions stay local.

The Club publishes metrics derived from accepted event rows joined to ingestion
receipts. Legacy client aggregate snapshots are not sufficient proof of request
membership. Completion/model-pair/stage claims need their own validated receipts.

## Terminal attempts independent of accounting

Services advertising `request_attempts_v1` in responses to signed status requests
also accept `request_attempts` in sequenced `sync` envelopes. Status requests are
signed; capability responses use the existing HTTPS connection. The client checks
this capability before queuing attempts, so older services cannot silently ignore
them. Ordinary usage sync continues if capability discovery is unavailable.

Each attempt contains `event_id`, `requested_at` (UTC day precision retained by the
journal), `request_health`, and optional `role` and consented `model_name`. The
health shape is unchanged, but attempts require a recorded terminal outcome:
`responded`, `failed`, or `cancelled`. Pending, synthetic and undispatched requests
are excluded. Missing duration is omitted. A failed call without complete usage
is eligible; reservations and invented zero token counts are never sent as usage.
No attempt field carries token totals, costs, prompts, source, paths, raw errors,
task identities or completion claims.

The attempt uses the same installation-scoped event ID as later usage for that
request. Separate local fingerprints track accepted attempts and usage. Up to 40
records total can travel in a signed sync, shared between both ledgers to avoid
starvation or oversized envelopes; attempts require an explicit accepted count
in the acknowledgment. Lost acknowledgments retain the exact envelope. Corrections
update the same event, and the public health aggregate selects the newest accepted
facts once per request. Token statistics continue to use only the usage ledger.

Existing sharing consent and the pre-consent baseline apply to both ledgers.
Resuming sharing excludes requests first recorded while paused; previously shared
attempts remain eligible for corrections and later reconciled usage. Model-sharing
revocation removes model and route detail at the service boundary, and old replays
cannot restore it. Disconnecting resets the attempt sync state alongside usage.

Deploy the service migration and signature/schema validation before releasing
the client. The service must enforce paired ownership, consent, sequence/hash
checks, receipt membership, same-ID ownership across both ledgers, and model
privacy before publication. The migration exposes readiness only after ingestion
and aggregation are installed. No production migration runs as part of client
startup. Validate rejection, correction, replay, missing acknowledgment, old-server
compatibility and privacy using deterministic local fixtures.

## Coverage limit

Health combines accepted terminal attempt records with legacy usage-only records,
deduplicated by request identity. It reports each coverage count separately. Older
installations and unshared/pre-consent history can still omit failed calls; do not
market this as provider uptime or a complete error rate. Success is the app's
recorded response outcome, not independent review or task completion. Signatures
authenticate the installation reporting a fact, not upstream truth. Attempt counts
and token totals have different coverage and should not be expected to match.

Validation: focused Club, journal, metrics, lifetime integration and startup tests;
no live model calls, service restarts or historical data edits.
