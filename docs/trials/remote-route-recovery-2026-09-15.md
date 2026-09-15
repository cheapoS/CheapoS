# Persistent remote routing recovery — September 15, 2026

## Behavior

Automatic remote placement now keeps looking within the authorized model pool
when an inference route fails. Availability failures do not consume the two
handoffs reserved for malformed model responses. Files, conversation, checks,
review progress, usage and spending authority are retained.

Discovery is paced at four uncached probes per 30-second round, not four probes
for the lifetime of a task. Failed candidate-specific HTTP 400/422 probes expire
after five minutes. Temporary transport failures back off for 30, 60, then 120
seconds. Reported provider cooldowns retain their scope and retry time. Unknown
reset times use a scheduled availability check, not a claim that quota has reset.
These are retry cadence defaults, not measured task-work caps.

Model-only failures do not blacklist healthy models on the same provider.
Provider-wide cooldowns also cover the `no-think/` alias. Gateway/catalog outages
wait and retry; rejected credentials require updating the client key in Models.
Pause cancels waiting. Limits and authorization still apply; automatic routing
does not silently enable paid or local fallback.

Saved route waits are restored at startup. Ordinary interrupted tasks are not
started automatically. Restart does not bypass expired verification permissions
or branch authority. Such a task still needs the existing review/start action.

## Live trial

Ran a real, one-item unattended job in a disposable repository with an
operator-prepared plan, `measurement: true`, automatic remote placement, no
included-model authorizations, and a zero-dollar policy. No synthetic failures,
model mocks, huge work caps, main-app restart, or user-task changes were used.
The test command was `python3 -B check.py` (three clamp assertions).

- Task: `de4587417408415f9c4a04b6c1046678`.
- Period: 20:27:04–20:29:03 UTC; controller elapsed 117.64 seconds.
- Change: fix the missing lower bound in a two-line `clamp` function.
- Worker: `antigravity/claude-sonnet-4-6`.
- Initial reviewer: `antigravity/claude-opus-4-6-thinking`.
- Recovery reviewer: `antigravity/gemini-3.1-flash-lite`.
- Result: item committed in the disposable feature branch; focused item and
  final checks passed; final independent review approved; ready for merge.
  The disposable branch was not merged.
- Interventions after Start: **zero**.

The run encountered four HTTP 400 probe failures from the two `auto/` routes,
one stream error, and six model-route cooldown failures (including the active
final reviewer). It crossed discovery rounds, waited automatically for 6.46
seconds, selected another reviewer, and finished. The original implementation
was retained. The two focused check executions were item and final verification,
not replays caused by routing recovery.

Usage: 27 request records, 102,979 accounted tokens (29,416 worker; 73,563
reviewer), estimated cost $0. There were 11 uncertain requests and 16 estimated
requests. These are app accounting figures, including estimates/reservations;
they are not a provider billing receipt or a count of confirmed billed tokens.

The raw task remains under
`/private/tmp/cheapos-routing-trial-20260915/profile/tasks/de4587417408415f9c4a04b6c1046678/task.json`.
No credentials are included in this report.

## Validation and limits

- Routing, model pool and cooldown modules: 55 tests passed in 26.57 seconds.
- Route health, transport and schedule subset: 37 tests passed in 0.027 seconds
  before adding one further pure transport-classification case.
- Updated model pool plus six scheduler cases: 28 passed in 11.35 seconds.
- Final scheduler/restart/cancellation subset: 14 passed in 2.82 seconds.
- Six new pure scheduler/state tests alone: 0.085 seconds.
- UI guidance: 54 tests passed in 0.102 seconds.
- Existing command-permission and credential checks passed. Two additional
  checks failed identically on unchanged main: the incomplete `limits` fixture
  in `test_manual_mutations_cannot_change_branch_contract`, and missing explicit
  full-suite consent in `test_real_three_item_run_exceeds_small_nominal_limits`.
  They were not weakened or folded into this routing change.

New tests use small state objects, mocks and fake clocks; no new multi-item Git
workflow or real-time sleeping regression was added. The live trial is manual
qualification, not an added routine test. The broad static selector included 96
Python modules because Engine is shared; focused coverage was used instead.
An initial run of an old cooldown test was interrupted because it expected a
terminal pause; it was updated to inspect and cancel the automatic wait.

This trial proves real recovery through several route failures and final review.
It does not prove every upstream outage, account topology, or restart scenario.
OmniRoute remains responsible for choosing credentials behind a model route;
cheapoS can only scope account failures from metadata it actually receives.
If every authorized route is down, work remains queued until availability or
an operator/time/spending stop. A malformed shared request or exhausted usable
independent-review pool still requires an actionable decision.
