# Restart task recovery, 2026-09-14

This is a supervised continuation of the user's restart feature, not an untouched
unattended qualification run. The latest run starts from `d7c1f9e` on
`feature/job-mu2302lo`. Earlier restart code was already on main; deleting a chat
and opening a new task legitimately includes committed code in its new snapshot.
It does not copy the deleted chat's private uncommitted files.

## Observed controller failures

- The worker was told never to finish with an empty patch, contradicting the
  controller's verified `satisfied_without_change` outcome. The instruction now
  permits submitting existing code for checks and independent review, without
  inventing edits or relaxing completion requirements.
- The compact context included a 500-path directory (about 13 KB in this repo)
  alongside current files, project facts and continuation evidence. That left
  little room under the 60 KB compaction trigger. The directory is now a labeled
  partial 60-path listing; active requirements remain intact and `list_files`
  can obtain additional paths.
- Reviewers could spend their last allowed request inspecting another file.
  The last request now offers the decision tool with the already collected
  evidence. It does not add requests or relax candidate/criterion validation.
- An OmniRoute `malformed_tool_call` placeholder was treated as an unsupported
  tool and spent model handoffs. The entire response is now rejected at the
  transport boundary. A streamed failure can use the existing once-per-route
  JSON retry, with both calls accounted. A successful fallback remains selected
  for later calls in that task.
- A pre-fix saved placeholder failure can resume that same bounded JSON retry.
  The local capability-mismatch cooldown from this misclassification does not
  defeat it. Provider/account/quota cooldowns, captured access policy, money,
  reviewer limits and consumed handoffs remain enforced.
- A routing stop raised directly during branch review lacked an error code.
  `RoutingPause` now carries `routing_unavailable`; reviewer stall diagnostics
  select the reviewer's request rather than the worker's implementation role.

## Supervisor interventions

The supervisor read the current task, supplied concrete corrections through its
chat, committed controller fixes, restarted the idle application to load them,
and reauthorized the same saved verification commands for the new server
session. No routing policy, model allowlist, paid fallback or cumulative work
allowance was expanded. The stopped legacy review was not declared approved.

A direct local POST with a valid JSON object confirmed the inherited endpoint
returns 200 and re-execs the server. Its bootstrap token changed. `os.execv`
preserves the PID; boot identity, rather than a different PID, establishes that
a new application instance is serving requests.

The inherited frontend still required correction: it omitted the JSON request
body and accepted the old server's first successful bootstrap response as
restart completion. Those are product defects independent of passing backend
unit tests.

## Provider failover and final outcome

Antigravity subsequently returned temporary availability/cooldown failures. These
were consuming the same two handoffs used for repairing a model's work. The
controller now records availability recovery separately (at most four provider
handoffs), skips the failed provider for the affected role in this request, and
tries an eligible alternative within the captured policy. Provider failures
during probes also skip sibling candidates. Account/connection quota boundaries
still stop work. The change does not expand access or permit paid fallback.

Failed availability calls no longer consume the eight substantive item-review
turns. The original network requests, usage reservations, and cumulative limits
remain counted. Exact candidate identity bounds which failures qualify.

Observed live result: the reviewer moved from Antigravity to
`openrouter/dots-studio/dots-3-note-preview:free`, through OmniRoute. It approved
T01's existing backend implementation, then T02's frontend edit. T01 has a
verified `satisfied_without_change` receipt. T02 was committed by cheapoS as
`0e038b2` on `feature/job-mu2302lo`.

The coordinator's T02 advice was rejected because the prose `poll /api/bootstrap`
was treated as a file reference. The validator now recognizes API polling
context throughout the bounded advice field. Typed file requests, traversal,
file suffixes and permitted-file checks retain their restrictions. A retained
path-rejected reply can be revalidated once on Resume without another model
call; stale replies still fail identity and current-file checks. In this live
run the worker made its edit after the supervised resume, before the final
validator correction was loaded; this run does **not** prove a live coordinator
rescue. The saved-advice path is covered by deterministic regression coverage.

Final aggregate review was **not completed**: after reviewing one requirements
chunk and requesting extra context for the next, the remaining reviewer-token
allowance could not fit the next conservatively reserved request. The controller
projected `BudgetError` as an unknown stop. It now classifies the typed error and
shows the relevant used/allowed allowance. No allowance was increased and no
uncertain reservation was refunded to force completion.

The supervisor integrated the independently item-reviewed feature with merge
commit `2fb967c`. Main had advanced while controller fixes were being made, so a
normal supervised merge preserved both histories; the app supports fast-forward
integration only. The supervisor then fixed remaining frontend failure paths:

- Compare the new boot against the token authenticating the restart request,
  rather than a best-effort preliminary bootstrap fetch.
- Bound request time, reject failed POSTs, and ignore old/invalid bootstrap
  responses. At most 30 polling attempts, separated by 500 ms, with a per-poll
  timeout; slow requests can extend total time beyond 15 seconds.
- Authenticate OmniRoute refresh and report failures instead of claiming success.
  Label that operation as a connection/catalog refresh, not a gateway process
  restart.
- Suppress overlapping restart actions and restore controls after failure.

Thus this is a working feature with **supervised completion**, not a claim that
the untouched unattended loop reached final approval or performed the merge.
The retained app run is left on its saved feature branch to preserve its actual
receipts and incomplete final-review history.

### Validation and cost

- The real task's accepted HTTP module passed (34 tests). Final verification also
  passed before aggregate review stopped. Its checks consumed 69.79 seconds in
  total; no new HTTP integration workflow was added.
- Provider/routing changes: 59 focused deterministic checks in 0.036 seconds;
  existing routing integration 25 tests in 27.020 seconds. The existing model-pool
  suite's changed expectations were corrected to require provider failover; the
  two affected cases then passed in 4.239 seconds (the other 20 already passed).
- Coordinator coverage: seven focused cases in 2.557 seconds using an existing
  fixture; the six pure contract cases subsequently passed in 0.006 seconds.
- Budget/pause/routing classification: 31 cases in 0.111 seconds.
- Six new browser-handler regression cases use Node's built-in test runner and
  simulated timers, with no real network or sleep. Standalone runtime: 73 ms.
  They run with the existing selected frontend checks. All 193 frontend checks
  passed in 116 ms, plus syntax checks.
- Computer-use verification ran against a separate app on port 5174 with
  disposable data, no model inference and a frozen copy of the candidate UI.
  The inherited UI reproduced the defect (page reload, same boot token). The
  worker's edit restarted the backend (different boot token, UI returned). The
  final combined refresh/restart action also changed boot identity and restored
  the UI. The user's executing task was not restarted by this browser test.

At the final live pause the run recorded 41 worker turns, 69 request records
(including pre-dispatch failures), 68 tool actions, 852,339 worker tokens,
170,676 reviewer tokens, four uncertain requests, about 899 seconds of active
work, and $0.00 accounted model cost. These are app accounting figures, including
retained reservations, not an upstream billing receipt. Supervisor development
and manual review are not included in those run totals.

### Follow-up evidence

Final review still repeats substantial per-criterion check/receipt data and can
spend context reads at the wrong end of a large file. Smaller evidence references
and symbol-targeted context would improve efficiency without dropping coverage.
Guidance arriving during review also needs an explicit pending/consumed state:
the supervisor's last frontend corrections arrived during T02 review and did not
get another worker turn before commit. The final reviewer claimed no JavaScript
test framework existed despite the repository's built-in Node tests. Treat that
as a review accuracy gap; passing Python checks alone cannot establish frontend
behavior. These observations should inform the next bounded qualification run.
