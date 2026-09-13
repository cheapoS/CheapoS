# First live Unattended trial: findings

Date: 2026-09-13. Specification: [Markdown run reports](unattended-run-report.md).

**Result: not an autonomous success.** Free workers produced an unfinished
formatter and test file. No item was approved, committed, or merged. The live
run is paused and its saved work is available for inspection. Fixes discovered
while operating the app are separate from the worker's feature code.

## Trial conditions and provenance

- Task storage was copied outside the source repository so cheapoS could work on
  its own code. The original `.cheapos` directory was retained because older
  task records still reference copies there. To reopen this trial's history on
  this Mac, launch from the project directory with:

  ```sh
  python3 -B run.py --data-dir "$HOME/Library/Application Support/cheapoS"
  ```

- Real free remote models through the user's local OmniRoute installation.
- $0 estimated spending cap; no paid or local inference fallback was used.
- Three dependent implementation items, twelve acceptance criteria, focused
  checks per item, and one final cumulative integration gate.
- Operator approval was given through the app's proposal and Start run flow.
  Feature commits were authorized; final merge and push were not.
- The observer prepared the executable three-item proposal from the committed
  specification after live planning repeatedly returned invalid proposals.
  Planning therefore was assisted, not autonomous.
- The observer fixed the app, restarted it between paused attempts, and gave
  explicit in-scope guidance during two execution attempts. The observer did
  not write or repair the requested report feature.
- Saved accounting reports $0.00. Some requests have estimated cost or retained
  uncertain reservations. This is not an independently verified provider bill,
  and no financial savings claim follows from it.

Across eleven saved proposal/attempt records, the app retained 123 request
records, 1,429,124 accounted worker tokens, and 131,981 accounted reviewer tokens.
The last attempt alone accounted for 692,003 worker tokens. None of these
attempts delivered a reviewed feature commit; token volume is not evidence of
useful completion.

## Reproducible app bugs repaired during the trial

| Failure | Repair | Commit |
| --- | --- | --- |
| Unattended planning dereferenced an unset worker; final review could similarly skip route selection. | Use the free-route selection and validation path for planning and final review requests, preserving their purpose and accounting. | `ed60a43` |
| Planner repair requests did not preserve the rejected tool call or explain its missing fields. | Send matching tool-error feedback and retain the rejected call in the repair conversation. | `a092d65` |
| Verification setup failure overwrote a complete proposal with its old planning placeholder. | Preserve the complete blocked draft and name the unavailable executable. | `68bb9f1` |
| Otherwise complete proposals failed because unused clarification metadata was omitted or null. | Normalize only empty clarification on an explicit complete plan; keep structural validation. | `c02b642` |
| A branch item with no edits yet was treated as an ordinary chat question during read-loop recovery. | Keep an active accepted item in implementation mode and retain action tools during recovery. | `2445e8f` |
| A missing test module produced a zero-test success. | Fail empty discovery and label the timing/JSON report unsuccessful. | `2445e8f` |
| Recovery queued at the checkpoint boundary was paused before getting a turn. | Permit one persisted recovery attempt within existing hard limits; Resume cannot renew it. | `58ad5ec` |
| Complete new-file writes were rejected by the blanket 80-line/3 KB edit cap. | Accept complete new files up to 24 KB; retain bounded versioned replacements, path protections, and rejection of incomplete provider responses. | `5f291ca` |

The new-file failure was observed on a valid 117-line, 4,607-byte response.
Increasing that bounded creation allowance let the next run save its formatter.
This does not authorize overwriting existing files or executing partial calls.

## Execution outcomes

The earlier planning attempts are saved in local task history. They exposed
missing envelope fields, omitted checks, prose in command fields, and a plan
expanded from three requested items into twelve. One prepared proposal was
correctly refused when a concurrent sidebar merge changed its committed base.

| Run | Outcome |
| --- | --- |
| `a6764415f1fb45ddab3ed0612050a083` | Answer-only recovery led into review without an implementation. The old runner incorrectly passed zero tests. Observer paused before any commit. |
| `81d9cd7b869f4e7c8bddda3bc4d92f79` | Repeated inspection queued action recovery at a checkpoint boundary; the controller paused before its first attempt. No files changed. |
| `3cfa513e5e3f4806b2196711db913ea3` | The worker repeatedly supplied complete new-file writes that exceeded the small-edit cap. Explicit chunking guidance did not recover it. No file was saved. |
| `2900ccbc25de4c9da817b84c7c55a713` | North Mini Code saved `cheapos/run_report.py` and `tests/test_run_report.py`, then repeatedly read or tried to recreate existing files. After operator guidance and 48 cumulative worker turns, it paused without a check, review, or commit. |

The final saved task is named **Trial: run report export — paused**, on
`feature/run-report-export-v4`, based on `5f291ca`. Its feature branch has no
feature commits; the two uncommitted files remain in its private task copy.
The source repository checkout does not contain this unfinished implementation.

The observer ran the exact focused test command in that task copy after it
paused. It failed during import with `ModuleNotFoundError: No module named
'cheapoS'`. The actual package is `cheapos`. Source inspection also found an
import of an absent `outcome_emoji` helper and invented report fields instead of
the saved run/receipt schema. Several tests mirror those invented fields.
These are unfinished code defects; the observer did not fix them to manufacture
a successful autonomous result. This independent diagnostic run was not inserted
into the app's verification or review records.

## Validation of the app repairs

- Routing, planning, HTTP planning/setup, and proposal repair regressions passed.
- The first repair passed the then-current full Python suite: 517 tests, 1,103.2 s.
- Later focused runs passed: 14 answer-recovery tests, 3 branch execution tests
  including a real read-loop-to-three-commits regression, 4 checkpoint-boundary
  tests, 4 work-policy tests, 3 test-runner tests, and 20 compact-edit tests.
- Frontend syntax and all 88 Node tests passed.
- The final cumulative Python run passed: 525 tests in 1,192.7 s (19 m 53 s),
  launched from `5f291ca`. The slowest individual test took 103.1 s.

The test-policy work is continuing separately on `work/faster-validation`.
Prefer focused checks for the behavior being changed during development; keep
the full suite as an explicit integration check rather than a repeated default.

No live model was used as an automated regression fixture. Those tests use
isolated repositories and deterministic providers; the live trial is separate.

## Next work, in order

### 1. Recover from an ineffective worker within the accepted run

Entry points: `cheapos/branch_controller.py`, `cheapos/engine.py`,
`cheapos/routing.py`, and `cheapos/model_pool.py`.

An HTTP-responsive model that can emit `routing_ready` has not demonstrated that
it can implement, test, and checkpoint. The branch controller currently pauses
after non-progress and resumes the same worker. Add a bounded alternative-model
path for observed implementation non-progress, reusing the existing free-route
machinery and visible handoff events.

Acceptance:

- A stalled worker can hand off the same private files, active item, review
  feedback, and accumulated usage to a different responding free worker.
- Use the accepted model-placement policy. Never change the paid/local policy,
  increase limits, overwrite task files, or reset cumulative allowances.
- Count these attempts in a durable per-item/run recovery allowance. Repeated
  Resume or restart must not replenish it. Stop with a useful explanation once
  alternatives or the allowance are exhausted.
- Exclude operator Pause, missing information requested with `ask_user`, failed
  environment setup, missing command consent, exhausted hard limits, and branch
  drift. These need their own recovery, not another model request.
- Record actual edit/check/checkpoint outcomes for branch workers in the model
  pool. Distinguish responsive tool calls from completed reviewed work.
- Inspect the context sent after compaction as part of this diagnosis. Preserve
  the current item, saved file names, latest tool errors, and relevant schema
  evidence. Do not assume a model swap fixes information that the controller
  dropped. Add a regression where a newly created file remains known after
  compaction and the worker is directed to its missing tests, not recreation.
- Cover a stalled worker followed by a successful different free worker, plus
  exhaustion, restart, no eligible alternative, and each excluded pause reason
  with deterministic provider fixtures and real isolated file/check operations.

### 2. Make planning repair useful before creating a blocked draft

Entry points: `cheapos/branch_planner.py`, `cheapos/branch_controller.py`, and
`dist/branch_ui.js`.

- Validate command fields as actual argv-compatible check commands during plan
  repair. Return the exact item/field problem to the planner; prose such as
  "No code changes made" must not become an executable name.
- Keep finite implementation items. Avoid automatically splitting every read,
  test, and review action into its own item.
- Make a complete draft blocked on setup editable in the proposal UI. It has no
  execution authority yet and should not offer a misleading Resume action.
- Re-inspection and Start remain the authorization point after edits. Preserve
  the original planning usage and show live planning progress while waiting.
- Test validation feedback and blocked-draft editing through the HTTP and UI
  boundaries, including stale proposals and changed committed bases.

### 3. Repeat a smaller live qualification before the full feature

Use a disposable project with a known small implementation and real tests. A
candidate worker must create a file, amend an existing file correctly, run the
agreed test, and submit a checkpoint. A distinct reviewer must return a valid
decision bound to the actual candidate. Observe a controller-created feature
commit without operator prompts between these steps.

Record model IDs, request count, elapsed time, actual test outcomes, the commit
receipt, and operator interventions. A responsive endpoint or a persuasive final
message is insufficient. Then retry the report specification, keeping failed
attempts distinct from a successful run.

Do not spend the next iteration merely increasing turn limits: this trial had
remaining hard allowance but repeatedly failed to choose the next useful action.
