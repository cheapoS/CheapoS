# Signed finished-work evidence v1

The first cohort is **new authorized unattended coding objectives**. Interactive
chat, historical tasks, route probes and unrelated discussion are excluded. This
is an installation-reported workflow outcome, not a code-quality certificate.

## Durable local evidence

`job_evidence.py` observes Store saves into the lifetime journal. A fresh objective
gets an opaque UUID before planning requests. Planning-to-proposal conversion,
retries, repairs and Resume retain it. A different run following a completed run
gets a different job. Existing chats are not retrospectively declared complete.
`GET /api/job-evidence` exports the deidentified local evidence for inspection.
The journal survives task/workspace removal and capped conversation histories.

Each dispatched, non-probe, non-discussion request carries its job ID. The journal
keeps the complete request set, including failures and planning before approval.
Reported `usage.cost` is retained as decimal text with currency (the compatible
API's USD convention unless an explicit currency is supplied). JSON decimal
spelling is preserved before float accounting. Missing charges are unknown;
reservations, configured estimates and access-category zeroes are not reported
charges. Existing local estimate/reservation accounting is unchanged.

Ready evidence requires the controller's final checks/review/acceptance flags and
matching candidate IDs. Acceptance additionally requires the explicit integration
authorization and completed merge receipt for that same candidate/operation.
Opaque wire IDs hide the Git references, commands and evidence contents. Repair
invalidates prior readiness; it cannot carry an old approval into new work.

Timing uses one mutually exclusive controller clock: active (including tools and
checks), provider-route wait, or operator wait. Authorization-to-ready elapsed and
ready-to-acceptance delay are separate. Parallel request durations are never
summed. Restarted unfinished jobs, clock reversal and replaced ready candidates
have partial timing and are excluded from complete timing medians.

Initial authorization, actual verification approvals and final integration are
routine approvals. API Resume and explicit operator revisions record rescue
signals. Internal automatic Resume is not an operator intervention. Ambiguous
chat and unknown caller attribution remain unclassified. API attribution is not
proof of human attention; unknown actors exclude a job from complete rescue
samples. External assistance not declared through a structured app action is
not observable. Zero means no rescue recorded in the observed workflow only.

## Separate consent and protocol

Finished-work sharing is **off by default**, separate from token and model-name
sharing. The Club preferences preview describes costs, timing, actions and the
forward-only boundary. Only jobs first observed after activation are eligible.
No model identities, prompts, paths, check commands or code enter this payload.
Pausing/disabling this sharing or disconnecting removes the server's job evidence.
The existing token-report retention policy is unchanged.

The signed installation protocol advertises `accepted_jobs_v1` only after its
service migration. Consent adds `share_jobs` (boolean) and `jobs_since` (UTC time
or null when disabled). The client checks capability before enabling or queuing.

A normal sequenced `sync` envelope can carry `job_page` with:

- `header`: version 1, job UUID, monotonically increasing revision, `started_at`,
  nullable authorization/ready/accepted timestamps, opaque candidate/acceptance
  UUIDs, state, three completeness booleans, exclusive clock milliseconds,
  rescue/approval/unclassified counts, `request_count`, and `page_count`.
- `index`: zero-based page index. Each page carries 20 members except the last.
- `members`: exact accepted request `event_id` membership, nullable decimal cost,
  nullable ISO currency, and `provider_reported` or `unknown` provenance.

A zero-request job has one empty page. Member IDs reuse the installation-scoped
UUIDs from signed request/usage reports. Requests must already have accepted
receipts and may belong to only one job. A durable snapshot/outbox freezes all
pages of a revision; a correction creates a new revision. Explicit
`job_pages_accepted: 1`, sequence and payload hash are required before advancing.
Outcome-only updates (including a merge after the last request) need no new tokens.
Unsupported services retain local evidence rather than silently consuming it.

The service validates signatures before its service-only transaction. It enforces
owner/pairing/consent, sequence/hash, exact schemas, request ownership, unique
membership, immutable pages within a revision and newer-revision corrections.
Public views require accepted receipts and current sharing. Missing pages or
charges suppress a complete-cost headline. Replaying old envelopes cannot restore
superseded facts. Deletion cascades remove dependent reports.

## Published cohort

Jobs are selected by UTC authorization date, observed through the response's
`as_of` timestamp. Known reported USD charges from **all** selected jobs, including
unsuccessful/open work, form the numerator. Divide by distinct accepted jobs only
when all membership and reported USD costs are complete and the denominator is
nonzero. Otherwise expose known subtotal and coverage, not a fabricated $0.
Non-USD requests remain identified as excluded currency coverage. Open cohorts
are provisional. Draft-only planning is reported separately.

The dedicated aggregate covers all eligible installations, not a leaderboard
sample. It returns timing and intervention medians with their eligible sample
counts, zero-recorded-rescue share, normal approvals, unknown actions, reporting
boundary, last update and installation counts. Subscriptions, hosting, hardware
and human time are excluded. Model-pair rankings are deferred.

## Rollout and validation

Install the companion service's accepted-jobs migration, then its capability-aware
API before enabling client consent. Existing token sync continues unchanged.
The client does not apply service migrations or enable reporting automatically.

Use focused `test_job_evidence`, Club, metrics, lifetime integration/request-health,
streaming and branch HTTP/authorization tests. New pure-data evidence cases took
about 0.01 seconds; no new full agent workflow, live inference or timed wait was
added. Companion SQL cases reuse its existing disposable database fixture (~25 ms
incremental). Validate signature tampering, partial pages, membership conflicts,
replay/correction, zero/missing costs, consent withdrawal, and outcome-only sync.
