# Continuous-session qualification — T84–T88

Date: 2026-09-15 (browser qualification continued after local midnight).
Baseline: local main `242e9ee`, including main's reviewer-memory, SSE empty
response and provider-cooldown fixes. Implementation: `6f98ac4`, `697b440`,
`f16c3c3`, `ed49f25`, plus this qualification commit.

## Result

Deterministic and disposable-browser qualification passed. This supports the
session/state transitions and preserved safeguards, **not** a real-model
completion-rate or token-saving claim. No live model comparison was authorized or
performed. No user task, real provider credential, or running app was used as a
fixture. No new full workflow regression or deliberate timed sleep was added.

## Acceptance evidence

| Scenario | Evidence | Outcome |
| --- | --- | --- |
| Explain, accept correction, answer without edits | Existing answer/steering tests; browser explanation before repair | Passed; soft checkpoint kept tools instead of forcing an early answer |
| Implement, check, actionable review rejection, repair, approve | Existing `test_branch_execution` three-item fixture, one REQUEST_CHANGES for missing notes | Passed; 3 feature commits, one revision, failed then passing check, no intermediate operator approval |
| Saved edit/check survives recovery without replay | Worker session interrupted-call cases, existing retest identity cases, existing worker-handoff integration; browser post-commit Pause/Resume | Passed; uncertain call outcome is data, not a redispatched mutation; unchanged check reuse keeps identity requirements |
| Compaction + restart retain remaining work/correction | New in-memory long-session serialization/continuation case and default/route-budget cases | Passed; exact instructions, next step and complete recent tool pair retained; historical reference searchable |
| Concurrent input during compaction | Injected mutation during immutable history capture | Passed; rejects stale checkpoint and retains new input |
| Commit then follow-up about completed work | Existing commit recovery/reconciliation checks plus actual disposable browser commit | Passed; source commit acknowledged and retained conversation answered follow-up |
| Limits and permissions | Existing checkpoint allowance/boundary, transport, starter scope and HTTP tests | Passed; no checklist or Continue granted permission, paid fallback or approval |
| Idempotent Continue | Pure busy-runtime policy cases, admission UI promises, browser Resume and plain `continue` | Passed; no new request segment for plain Continue; no repeated check/edit |

Compaction measurement on a synthetic 22-message transcript: 201,347 serialized
characters reduced to 17,211 (5 messages) with an 18,000-character route budget.
Full source remains retrievable. This is a fixture measurement, not a token or
completion benchmark. Capacity too small for exact requirements reports an error
instead of silently losing instructions.

## Disposable browser run

`127.0.0.1:5298`, temporary data, deterministic worker/reviewer, tiny clamp repo.
The existing sample fixture's command discovers only its three tiny sample tests;
it is not the cheapoS repository suite. That check took 0.11s. The browser run
contained one source read, one mutation, one verification and one approved local
commit (`a5ec45e3` in the disposable repository).

Observed Send and Enter acknowledgments, a saved working checklist, actual
answer, passing checks, reviewer feedback and final Approve & commit. Details
remained expanded and an unsent draft remained intact across Tests → Chat.
After commit, an interruptible scripted response allowed Pause, then Resume;
a second Pause was resumed with plain `continue` in chat. Both settled with an
answer and editable composer; no spinner remained. The final saved record had
one check and one commit, four substantive user requests (Continue did not add
a fifth), and 220 synthetic accounted tokens: worker 200, reviewer 20, cost $0.
There were no live model requests. Manual browsing time is not a throughput
measurement; the interruptible provider used the stop event, not a timed sleep.

Issues found and fixed during qualification:

- Current working state was rendered only for branch replies; ordinary chat now
  renders it on its latest response, even without a tool card.
- An earlier next action could survive a new direction/commit as current advice.
  Its identity now becomes historical and it cannot override current recovery.
- Interactive sends cleared only the in-memory draft, leaving the shared work-mode
  persistent draft behind. Successful delivery now clears the matching stored
  prompt, preserving newer drafts. Browser reload verified an empty composer.
- Old test providers assumed all context was in the first/last message. Fixtures
  now inspect retained context; assertions for files, approval, scope and commits
  remain. The existing full-suite-consent policy is explicitly acknowledged in
  the tiny integration fixtures, not bypassed in product code.

## Focused validation and cost

The selector was run. Its engine reverse-dependency selection reaches 110 modules;
we deliberately used affected modules and existing integration coverage instead
of a full-suite run. Successful runs included:

| Check group | Time |
| --- | ---: |
| Existing branch execution (3 cases, including multi-item repair) | 43.554s |
| Existing worker recovery integration + 3 policy cases | 9.309s |
| Existing work policy (4 cases) | 1.183s |
| Existing answer recovery (15 cases) | 7.421s |
| Existing operator controls / progress / checkpoint boundaries / allowances | 1.789s / 2.505s / 5.564s / 0.014s |
| Working/session/context/operator/retest/steer group (46 cases, overlaps above) | 9.464s |
| Transport, context observations, project/recovery context, tool arguments (37) | 1.559s |
| HTTP, starter scope, execution context (45) | 12.640s |
| Conversation, branch and admission JavaScript tests (83) | 90.8ms |

New tests are pure/mock cases, not additional Git workflows: two conversation
cases <0.001s; two working-state cases <0.001s; two original compaction additions
<0.002s; four continuation cases 0.015s (0.066s with cold imports); long-session
restart/concurrent-input case 0.011s; conversation rendering case ~0.6ms. They run
with their affected modules. JavaScript syntax and `git diff --check` passed.
Initial fixture failures and the UI issues above were corrected and their affected
checks rerun; unchanged passing multi-item coverage was not repeated for the merge.

## Remaining limits / next evidence

Live comparison remains pending explicit task, route and spending selection.
Use `measurement: true`, preserve free-only policy when selected, and log failures,
interventions, actual served model, tokens/cost, uncertain usage and timing. Do not
claim automatic success for manually finished work. Provider quality and outages
remain independent risks; memory continuity does not guarantee a model follows
instructions. Historical output is currently kept in the task file, so disk size
can grow. The checklist is optional and advisory, never proof that a step passed.
