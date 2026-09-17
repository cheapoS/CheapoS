# Routing recovery investigation — September 17, 2026

Reviewed the seven commits through `4cfc6ac`, including the recent planning,
provider rotation, and recovery changes. This is a debugging record, not a live
qualification run. Personal task data and provider response bodies are not
included here.

## What failed

Retained OmniRoute logs showed a Groq planner answering six inspections, then
returning HTTP 400 on `propose_branch_plan`: `plan` was an array rather than an
object, and `constraints` was an undeclared outer field. CheapOS reduced that
diagnosis to a generic HTTP error and attempted a model handoff. Later routes
encountered genuine OpenRouter rate limits and an unavailable NVIDIA route.
One malformed proposal therefore looked like a series of broken connections.

Recent catch-all review recovery also converted budget, evidence, and controller
errors into reviewer retries. The selector invented five-second retry schedules
for pauses without a reset time, including conditions needing operator action.
Meanwhile, background planning did not enable the selector's existing scheduled
availability recovery.

## Repair boundaries

- Preserve provider-first failover for outages and quota failures. Keep the
  provider interleaving, reasoning-field cleanup, and planning inspection fixes.
- Recognize an upstream tool-validation rejection using bounded metadata and an
  app-authored diagnostic. Never retain `failed_generation` or arbitrary error
  bodies. Ordinary HTTP 400 responses remain distinct.
- Give a rejected proposal to the planner's existing bounded correction loop.
  Retain its request, inspections, accounting, and model; repair the declared
  envelope instead of loosening the schema. After correction attempts are
  exhausted, existing eligible-planner recovery still applies.
- Let centralized routing handle transport failover. Preserve budget, evidence,
  authentication, and controller failures rather than swallowing them in review
  loops or relabeling them as reviewer-identity failures.
- Enable scheduled availability recovery while planning. Do not invent a reset
  time for an unscheduled pause. Existing quota backoff remains available.
- Stop on a model refusal rather than sweeping providers for a different answer.

No access policy, paid-model authorization, task allowance, gateway credentials,
or saved health observations were reset.

## Validation

New coverage uses fake responses and immediate mocked waits: **10 cases in
0.010 seconds**. It exercises the actual routed planner and proposal parser,
saved inspection context, bounded correction, usage retention, scheduled waits,
and preservation of non-routing failures.

The existing remote-planning HTTP test now injects one upstream rejection before
a valid proposal. It passes in **1.701 seconds**, retains the failed request's
uncertain reservation, dispatches only to the same model, and still requires
operator authorization before creating the feature branch. The existing async
planning cancellation case also passes. No new server/Git fixture or timed wait
was added. These HTTP checks use temporary repositories and fake providers.

The first broader focused run covered 177 existing cases in 43.821 seconds and
found three failures. All three also failed on an untouched archive of
`4cfc6ac`. The recent refusal-failover regression was repaired and its existing
case now passes. Two pre-existing failures remain outside this repair:

- `test_routing.RoutingTests.test_three_identical_reads_allow_one_answer_request_without_tools`
  expects `answer_pending` after repeated reads; the current engine clears it.
- `test_model_pool.FailoverTests.test_unavailable_tool_during_action_recovery_hands_off_without_executing_any_calls`
  expects a worker handoff; the current engine continues on the original worker.

Their assertions were preserved. The broader run included transport, provider
pacing, quota cooldown, provider rotation, review receipts, and worker recovery.
A final planning-focused run passed all 36 cases in 1.756 seconds, including
proposal parsing, recovery, allowance handling, and planner accounting.
Full-suite validation and live provider inference were not performed. Successful
local fixtures establish controller behavior, not upstream service availability.
