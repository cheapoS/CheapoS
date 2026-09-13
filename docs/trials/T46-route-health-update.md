# T46 route-health update

Tool probes now require the exact `cheapos-tool-check-v2` marker through the
existing parser. HTTP success, empty arguments, extra fields, and reasoning alone
cannot satisfy this contract. Old probe facts remain historical observations but
cannot satisfy the new version/configuration fingerprint. Fingerprints include
endpoint, exact model, opaque connection revision, probe contract, and relevant
catalog capability/limit fields; no key or secret-derived token is stored.

Fresh matching checks retain the existing five-minute lifetime. Cooldown state
always wins over earlier success. The existing pool shares identical in-flight
probes using owner/event leases, released in `finally`, with at most four probes
in flight. Waiters wait interruptibly and do not incur another probe reservation.
If the owner fails or cancels, no success is fabricated. A full probe queue pauses
selection without marking the model broken. There is no background model scan.
Actual request observations retain their source/time; a plain successful request
is not silently upgraded into a successful marker-tool check.

A shared classifier emits sanitized category, scope, retry, quality impact, and
operator action. Credentials affect only their connection revision; caller errors
and cancellation do not penalize model quality. Quota/provider transport issues
are availability evidence, not coding-quality failures. Provider/account scope is
retained only when structured input establishes it. Unknown reset/quota values
remain unavailable. Identity-separation failures request a different verified
reviewer without labeling the model's output malformed.

Catalog metadata carries `metadata_evidence` with source, observation time,
changed capability/limit field names, and staleness. Drift reports do not rewrite
pricing, grants, or task plans. This uses existing gateway discovery only; no new
external catalog or credential fetch was introduced. Routing traces distinguish
exclusion reasons, unknown fit, needed/cached/shared probes, final selection, and
post-response probe validation failure. Context rejection requires an explicit
known requirement exceeding a known limit; no token-history proxy is invented.

Validation used 124 distinct existing/focused tests across route health, access,
routing, model pool, gateway, cooldown, output recovery, compact edits, branch
planning HTTP, and branch worker recovery. All passed after fixtures adopted the
required marker/current scoped cache identity. Six new deterministic health cases
cost 0.003s under the module runner (0.028s with standalone import initialization).
They use no Git, inference, real waits, or additional server fixture. Existing
parallel module groups completed in about ten seconds. Final classifier additions
were rerun in the tiny module. No full suite or live inference was run.

Limits: capability checks establish their explicit tool contract, not coding
quality or current spending permission. Missing upstream quota/served-attempt
metadata is not inferred. In-flight sharing is process-local; a restart discards
leases. Catalog drift history compares consecutive successful refreshes rather
than claiming an authoritative external model history.
