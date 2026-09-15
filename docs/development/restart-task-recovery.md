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
