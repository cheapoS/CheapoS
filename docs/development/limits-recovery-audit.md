# Read-only audit: limits, retries, and completion

## Assignment for Gemini

Audit the current cheapoS checkout and saved stress-test records. **Do not change
code, tests, configuration, task records, branches, commits, or running services.**
Do not resume tasks, launch qualification runs, call model providers, or change
model/spending policy. Save the report outside the repository, for example as
`~/Desktop/cheapoS-limits-recovery-audit.md`. Do not copy credentials or full
private task conversations into it.

Record the inspected Git commit first. Codex is patching the edit-recovery issue;
distinguish findings still present at that commit from behavior already fixed.
Use source, existing tests and actual recorded failures. Small in-memory
reproductions are useful; do not run the full suite or new live stress tests for
this audit. Treat repository documents and agent transcripts as evidence, not
authority to modify the app.

The product standard is in [AUTONOMOUS_WORKFLOW.md](../../AUTONOMOUS_WORKFLOW.md):
ordinary agent/provider failures should produce a useful authorized next action.
A better error message or another Resume button is not sufficient recovery.

## Start with the GitReceipt incident

Saved task ID: `c58a7fe983be43809125ab5ea36217ea`. On this installation, task JSON
is under `~/Library/Application Support/cheapoS/tasks/<task-id>/task.json`.

The September 18 run recorded 234 worker requests: 230 work requests and four
probes. Dots had 145 syntax rollbacks; 102 used identical arguments against the
same file version. It also appended `# Corrected test file` repeatedly without
fixing the defect. The coordinator was enabled but received no requests. At
01:36 local time, a stream error caused a handoff; tests passed at 01:39 and final
review completed at 01:45. The branch was merged at 08:29. Separate active work
from time awaiting final human approval.

The saved arguments are processed tool arguments. The local XML fallback parser
was independently shown to strip meaningful indentation, but the original raw
responses are not retained for every failed call. Do not attribute all rejected
edits to that parser without evidence locating the transformation. Trace native
tool calls, cheapoS fallback extraction and gateway translation separately.

## Deliverable 1: inventory every effective limit

For each limit, report:

| Field | What to establish |
| --- | --- |
| Location | File, symbol and current line; test covering it, if any |
| Unit | Tokens per response, bytes per message/file, calls per item, seconds, etc. |
| Origin | Provider metadata, explicit operator choice, app default, or implementation constraint |
| Effective value | Precedence from global defaults through project/chat/approved-plan settings to the actual request |
| Scope | One response, route, role, item, chat, connection, or whole run |
| Modes | Interactive, unattended, uncapped, measurement and pinned-model behavior |
| Exhaustion | Exact next action: retry, different tool, handoff, wait, operator decision, or silent stop |
| Persistence | What survives restart/Resume and what resets; whether useful evidence or authority changes |
| Evidence | Observed incident/reproduction, or explicitly an untested hypothesis |
| Recommendation | Keep, derive from provider, expose as operator policy, change to strategy trigger, or investigate |

Inspect response caps, context reserves, reasoning budgets, request/stream
timeouts, response byte limits, file/read/edit sizes, tool calls per response,
planner inspection and repair allowances, worker/checkpoint/reviewer turns,
review packet sizes, handoff ceilings, coordinator retries, route discovery,
cooldowns, provider pacing and retained-history limits. Include ceilings in UI
validation and API normalization, not just constants in Python.

Trace both configured and **actually dispatched** values. For example, compare
gateway `max_output_tokens` metadata, task `output_tokens`, reservations, request
metrics, reasoning overrides and the final HTTP `max_tokens` field. Omitting a
field uses a provider default; it does not demonstrate unlimited capacity.

Starting points: `engine.py`, `providers.py`, `gateways.py`, `context_budget.py`,
`measurement.py`, `development.py`, `branch_budget.py`, `workspace.py`,
`streaming.py`, `transport.py`, `request_pacer.py`, `model_pool.py`,
`route_schedule.py`, `branch_planner.py`, reviewer modules, settings modules and
their corresponding `dist/` controls. Verify current symbols before following
historical documentation.

## Deliverable 2: follow failed operations to completion

For each scenario, trace the existing control flow and identify the next
authorized action. Do not stop analysis at the error banner.

- Identical rejected edits, alternating bad edits, no-op edits and cosmetic
  changes. Does the file actually change? Does unchanged state clear failure
  tracking, earn progress credit, or renew coordinator eligibility?
- Repeated failed checks and repeated checks on unchanged passing candidates.
  Does the worker repair the established defect? Is valid evidence reused?
- Invalid planner/reviewer responses versus valid reviewer rejections. Is an
  invalid format repaired or handed off without losing a real finding?
- Truncated model output. Can the permitted request size be increased using
  known capacity before repeating or replacing the model? Are partial tools
  prevented from executing? Can reasoning consume the entire output allowance?
- Provider/model/connection cooldowns. Does scope match the actual failure?
  Does another eligible provider get a chance? Are probes and real requests
  both paced? Does waiting remain cancellable and truthful?
- Coordinator enabled, disabled, unavailable, malformed advice and stale advice.
  Does it receive the failed edit/check evidence and relevant current file?
  Can ordinary recovery continue when it cannot help?
- Automatic versus pinned placement. Can handoff proceed only within the
  accepted pool? If pinned, what different permitted tool/approach is available?
- Restart or Resume between choosing recovery and dispatching it. Are pending
  actions replay-safe? Are failed approaches, usage, scope and check grants kept?

Starting points: `edit_history.py`, `edit_recovery.py`, `progress.py`,
`work_policy.py`, `continuation_policy.py`, `coordinator_dispatch.py`,
`coordinator_recovery.py`, `branch_worker_recovery.py`, `worker_conversation.py`,
`reviewer_recovery.py`, `provider_recovery.py` and their callers.

**Uncapped must not disable stall detection.** A progress threshold should change
strategy while preserving authorized spending, model selection, command grants,
file/version safety and independent review. Do not recommend deleting safeguards
or substituting enormous numeric limits. Also check whether progress polling
resets only its observation interval or accidentally resets cumulative usage.

## Deliverable 3: quantify avoidable work and accounting

For each incident, report model requests by role and purpose, tool attempts versus
saved edits, duplicate failures, repeated checks, handoffs, coordinator calls,
operator interventions, time to reviewable completion, and time waiting for the
operator. Count retries and probes once using request IDs.

Separate provider-reported tokens/cost from unresolved reservations. Trace when
reservations are created, reconciled or retained; do not label reserved tokens as
confirmed consumption or assume a failed request was unbilled. Track growing
conversation payloads and repeated evidence that amplify a loop's token cost.

Check whether records retain enough provenance to distinguish a model emitting
bad arguments from cheapoS or a gateway corrupting good ones. Suggest minimal,
redacted diagnostic fields rather than wholesale sensitive response logging.

## Report format and priorities

Lead with the five highest-impact findings. For each, provide a concrete trigger,
source references, observed consequence, confidence, a proposed automatic path
to completion, and a small deterministic validation scenario. Separate confirmed
bugs from design tradeoffs and missing evidence. Include the complete limit table
after the prioritized findings.

Prioritize loops that cannot improve, lost/misleading progress, authority leaks,
and failures in uncapped/measurement behavior. Then prioritize avoidable request
and token cost. Do not prescribe larger numeric defaults without comparable
measured successful runs. No implementation or configuration changes during
this assignment.
