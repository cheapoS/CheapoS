# Task records and optional diagnostics

The saved task keeps the information needed to continue work and account for
requests. Verbose routing traces and structural adapter measurements live in
separate local diagnostic snapshots. Losing diagnostics must never remove work,
reset authorization or turn a pending review into an approval.

## Storage boundary

| Durable task record | Optional diagnostic snapshot |
| --- | --- |
| Conversation, plan, actions and operator directions | Routing candidate scans and attempted routes |
| Current operation, recovery state and attempt history | Routing request diagnostics |
| Check evidence, reviews, patches and commit information | Structural wire, extraction, argument and edit measurements |
| Model choices, permissions, spending limits and reservations | Existing diagnostic truncation marker |
| Request IDs, dispatch/outcome, usage, cost and evidence fields | Structural measurements indexed by request ID |

Only `routing_traces`, `routing_traces_truncated` and the
`structural_telemetry` field of request records move out of `task.json`.
Execution-relevant events remain in the task even when they also help explain a
failure. `routing_trace_sequence` remains durable to preserve trace identity.
Request accounting is not subject to diagnostic cleanup.

Each task references an immutable, content-addressed snapshot in its own
`diagnostics/` directory. The store writes that snapshot first, then atomically
replaces the task record. Only after a successful task write may it remove
superseded snapshots. A failed task write leaves the previous reference valid;
a failed diagnostic write preserves the details inline and still saves work.
Unchanged diagnostic content is not rewritten.

Existing tasks can still use inline diagnostics. Their next successful save
migrates the fields. Startup and ordinary task polling do not read snapshots.
Runtime task reads restore the optional details so existing diagnostic writers
continue to work. Missing, damaged or unsupported snapshots produce a diagnostic
notice while leaving execution, checks, reviews and accounting available.
References accept only the supported version and a SHA-256 digest, verify the
content hash and reject symlinked diagnostic paths.

This change preserves existing diagnostic row limits. It does not introduce a
new retention deadline, task retry limit or execution budget. Configurable
diagnostic retention can build on this boundary later. Active runtime tasks
still hold diagnostic data, and saving changed diagnostics still requires
serializing it; this is not a complete rewrite of runtime logging.

## Browser and exports

Normal task responses omit routing traces and structural measurements. Technical
logs fetches routing selections separately, eight per page, with older/latest
navigation and an explicit retry after a failed load. The browser caches by task
and diagnostic revision; late responses cannot replace a different task's view.

- **Copy task JSON / Export JSON** produces a versioned task summary: actual
  steps, check and review summaries, changed paths, status and usage. It omits
  routing noise, raw check output and the working-copy path. Task text can still
  be private; the export is neither a resumable backup nor proof for public stats.
- **Technical logs → Download diagnostics** exports the retained local routing
  and structural data separately. This is troubleshooting information and may
  identify configured models and routes. It is not automatically uploaded.
- The complete local task record remains the execution source of truth. Backups
  that need diagnostics should include the task directory, not only `task.json`.

Session activity retains the existing total number of dispatched calls. Where
available, each role now distinguishes task requests from connection checks
(`purpose: probe`). Failed dispatched probes still count; undispatched records
do not. Missing historical purpose or missing retained rows appear as
**unclassified**, never as invented planning or review work.

These counts are local projections, not a new public metric. The existing
installation signature, consent, stable event identity, correction/replay and
server acceptance requirements for [signed request health](signed-request-health.md)
remain unchanged. Diagnostics and copied task summaries cannot establish
accepted request membership, task completion or public token totals.

## Focused verification

Small deterministic storage/HTTP tests cover migration, accounting preservation,
restart, missing/corrupt snapshots, interrupted writes, reference confinement,
pagination and separate exports. They use temporary data without models, sockets,
Git workflows or waits. The nine new cases ran in 0.04 seconds on the development
machine. A metrics case checks probe classification without altering totals.
Five new JavaScript cases cover lazy loading, explicit retry, stale responses,
summary copying and session counts; their combined case time was about 3 ms.

Broader focused coverage exercises polling, lifetime and signed evidence,
recovery, storage maintenance and HTTP behavior. Browser verification uses a
disposable profile and synthetic requests to check pagination, diagnostic
download and the session breakdown without calling a provider.
