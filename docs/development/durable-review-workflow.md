# Durable review workflow

The reviewer should judge a small, explicit question about the current change.
The controller should remember the answer, schedule unresolved questions, and
establish when the whole review is complete. Repeatedly asking a model to rewrite
an expanding final report made response formatting and repeated inspection an
increasing part of the work. A successful small capability probe did not predict
whether a model could finish that report.

## Execution contract

Evidence-enabled final review now has a versioned, durable workflow:

1. Freeze the current candidate, original requirements, operator directions,
   verification receipts and verification environment through the existing
   manifest/readiness machinery.
2. For a small task, ask for one complete review. For a larger task, partition
   every requirement into groups of at most four and roughly 4,000 characters,
   keeping item boundaries. A single larger requirement is retained intact.
   These are payload sizes, not work or retry limits.
3. Each requirement unit receives a small evidence catalog, exact delivered
   excerpts and readers for missing context. The model supplies judgments and
   short evidence handles. The controller supplies manifest and coverage IDs.
4. Persist each explicit, validated independent approval before dispatching the
   next unit. A provisional assessment, successful read, passing test or model
   summary never approves a unit.
5. Require an integration review of interactions, regressions, verification
   coverage and limitations. It can reject the change even when every individual
   requirement passed. Small tasks perform this in their complete review.
6. Compose the final receipt deterministically from the complete set of current
   unit approvals. No additional model request rewrites all the same judgments.
   Existing readiness, source identity, check and operator integration gates
   still apply.

Requirement units do not run commands, edit files, select more expensive models,
change approved scope or grant merge authority. Behavioral judgments require
source/document or visual evidence; a check-only criterion uses its exact
matching current command receipt. Models must explain the evidence's limits.
Provenance validation cannot determine whether a model's judgment is correct.
Visual and interaction checks remain necessary for claims that depend on them.

## Persistence and recovery

`review_workflow.py` owns deterministic unit definitions, scheduling and receipt
composition. `review_unit.py` owns the small model-facing protocol.
`branch_final.py` supplies the existing exact-candidate tools and validators.
The registered `review_unit` instruction profile describes reviewer behavior;
it does not confer tool or execution authority.

`branch_run.review_workflows` retains each workflow basis, completed unit
receipts, active unit and outcome. The basis includes the manifest, current
review inputs, checks, protocol version and unit definitions. Resume validates
completed receipts and continues the first unresolved unit. Changed code, scope,
directions or check bindings create a separate workflow; old records remain.
Existing exact chunk approvals remain reusable. Historical repair descriptions
do not become fresh requirements.

Authorized model handoff retains evidence, provisional claims, completed units,
usage and cumulative failures. Format failures for this materially different
protocol use one versioned recovery scope for the entire manifest, shared across
units and Resume. Legacy format failures remain archived. Provider health,
served identity, model pins, spending and command permissions remain enforced.
An operator-pinned model is not silently replaced.

Identity recovery retains its full attempted-route history and separately records
routes that returned a valid actual response. A later failure or interrupted
dispatch revokes that eligibility. Older records may restore it once from the
latest actual, identified response on the same saved connection revision; missing
provenance, later failures, synthetic records and probe success cannot establish
it. The current protocol's format exclusions and live health still filter every
selection, and every new response must establish independence again. This avoids
carrying an old format failure into a new protocol as a permanent identity ban.

Outgoing unit conversation history retains up to 16,000 characters of complete
exchanges; older exchanges remain readable by local reference. Initial delivered
evidence is at most 12,000 characters, with individual excerpts at most 4,000.
These limits bound repeated context, not accessible evidence. Large sources
remain pageable. Unknown or stale short handles are rejected. Conflicting
model-supplied coverage is rejected rather than silently repaired.

## Research and design choices

| Reference | Useful mechanism | Application here |
| --- | --- | --- |
| [OpenSpec](https://github.com/Fission-AI/OpenSpec) | Explicit proposal, requirements, scenarios and implementation tasks | Preserve approved scope and original requirement identity throughout execution. A spec document alone does not schedule or terminate review. |
| [aigit](https://github.com/hardiksondagar/aigit) | Review a staged diff with one model request and display the result | Keep model-facing review simple. Its review command does not provide the durable autonomous review/repair lifecycle needed here. Source inspected at `8b99165246618ccf352757a6d0bb704d3d71273d`. |
| [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | Checkpoints and preservation of successful steps across a failed continuation | Save completed units and resume unresolved work without replaying approvals. No framework dependency is added. |
| [Anthropic: effective agents](https://www.anthropic.com/engineering/building-effective-agents) | Simple workflows with explicit boundaries and evaluation criteria | Controller-owned scheduling, model-owned judgment and a separate integration decision. |
| [Anthropic: long-running harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | Durable progress, incremental work and actual end-to-end verification | Preserve evidence across sessions and distinguish a completed checklist from verified product behavior. |
| [OpenHands verification stack](https://www.openhands.dev/blog/20260506-the-verification-stack) | Separate review and functional verification responsibilities | Preserve source review and captured checks as different evidence types; do not label static inspection as runtime QA. |
| [Aider lint/test workflow](https://aider.chat/docs/usage/lint-test.html) | Feed actual command failures into repair | Keep check outcomes grounded in executed commands; don't ask a reviewer to invent success from a plausible diff. |

These are architectural references, not a claim that another project has solved
our model/provider conditions. This implementation uses the existing Python
controller and imports no external orchestration framework or third-party code.

## Validation and rollout

In-memory scripted cases exercise 23 requirements through six requirement
reviews plus one integration review, cancellation/JSON reload, automatic handoff,
invalid references, missing coverage, tampered receipts, changed directions and
checks, integration rejection, mixed read/decision batches, and retained oversized
responses. They invoke the actual request assembly and decision validators with
scripted responses. They establish control flow and authority, not model quality.
Existing Git execution, final-readiness and recovery tests cover repository and
check integration. The twelve new cases take approximately 0.08 seconds
combined locally, without Git, network calls, sleeps or paid inference.

Legacy review receipts remain supported. Already-running legacy final synthesis
can enter the new workflow without erasing its history; prior chunk approvals,
implementation commits, passing checks, usage and permissions are retained.
Interactive checkpoints and ordinary item review keep their existing lifecycle.

Qualify with a paused real run only with operator authorization. Record a fresh
baseline: actual review requests separately from probes, new input/output tokens,
provider failures, distinct reads, accepted judgments, completed units, handoffs,
repairs, elapsed time and operator interventions. A reduction in JSON errors is
not enough: the task must reach a supported rejection/repair or a valid final
operator decision. Do not count old cumulative calls as new failures, treat a
long in-flight request alone as a loop, or increase limits to manufacture success.

Future changes should preserve this completion contract. Next priorities are
measuring real per-unit completion, narrowing evidence retrieval to unresolved
questions, testing review quality against seeded defects, and reusing unaffected
judgments across repairs only with demonstrable dependency evidence. Do not infer
independence merely because changed files differ. Public metrics still need the
separate signed-evidence contract; these local records are not public statistics.
