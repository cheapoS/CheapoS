# T52 — Keep unattended execution separate from conversational behavior

Status: Completed
Priority: High
Depends on: current unattended setup and independent-item scheduling
Size: M
Planning baseline: `4b6ed68`, September 14, 2026

## Outcome

After Start, cheapoS works through the approved plan without asking permission
for work already authorized or finishing an item with a conversational answer.
Essential missing decisions still become explicit, durable blockers. Interactive
chat and proposal planning continue to support normal questions.

## Current evidence and files

Read [engine.py](../../cheapos/engine.py), especially initial/compact/action
messages, near-limit handling, offered tools, returned-tool dispatch, and no-tool
responses. Also read [unattended_setup.py](../../cheapos/unattended_setup.py),
[branch_controller.py](../../cheapos/branch_controller.py),
[work_policy.py](../../cheapos/work_policy.py), and
[branch_runs.py](../../cheapos/branch_runs.py).

Several prompt/tool choices already use `conversational and not branch_run`.
Other paths still check `conversational` alone, including near-end answer
handling, repeated-read guidance, and returned `ask_user` calls. Audit these by
purpose; some counters legitimately apply to both modes. A missing tool in the
advertised schema does not itself prevent its execution by the dispatcher.

## Work

1. Define one small execution-context helper that distinguishes interactive chat,
   unattended proposal planning, authorized unattended work, and review. Use it
   consistently at behavior boundaries. Do not turn off the saved `conversational`
   flag globally: the user still interacts through the same chat UI.
2. Apply that context when building initial, compacted, recovery, handoff, and
   resumed prompts. Unattended prompts retain the current item, requirements,
   permitted checks, review feedback, and saved progress. Near-limit and repeated
   read guidance must not suggest tools absent from the current mode.
3. Validate returned tool names against the tools actually offered for that
   request before dispatch, including outside compact recovery. A stale or
   invented `ask_user` cannot silently move execution into interactive mode.
   Return bounded corrective feedback through the existing recovery mechanism.
4. Preserve a supported way to submit a real blocker. Reuse the controller's
   `waiting_for_user`/blocked-item storage and independent-item scheduling. If no
   suitable execution tool remains, expose a narrow `report_blocker` tool for
   unattended work with the question, inspected evidence, and why an essential
   decision remains. Do not re-enable all `CHAT_TOOLS` merely to obtain it.
5. Use the existing reconsideration policy for questions answerable from the
   repository. Permit sensible reversible choices within scope and record them.
   A genuine unknown, unavailable prerequisite, or request for additional
   authority must remain blocked and visible; never invent the user's answer.
6. Preserve existing clean-workspace rules for continuing independent items.
   Do not start dependents of a blocked item, skip dirty partial work, or broaden
   commands, installation, external actions, or spending authorization.
7. Text such as “All done” is progress commentary until required verification,
   independent review, and receipts establish completion. Compaction, a restart,
   and switching from planning into execution must retain that distinction.

## Acceptance

- Interactive greetings/questions still work; pre-Start planning can clarify scope.
- An authorized branch worker retains its execution prompt and tool policy after
  compaction, recovery, handoff, and resume.
- An unoffered conversational tool is rejected before changing task state. A
  text-only completion does not become an approved item or bypass review.
- Already permitted checks do not trigger redundant conversational permission
  requests; genuinely new authority still requires the existing approval path.
- A real blocker is saved with evidence and can receive an operator reply later.
  Eligible independent items continue only under the existing safe conditions.
- Old saved tasks remain readable and do not gain new authority on restart.

## Focused validation and handoff

Start with the selector plan. Prefer table-driven context/tool-policy tests and
captured synthetic request packets over whole agent runs. Reuse affected existing
cases in `test_chat.py`, `test_answer_recovery.py`, `test_compaction_observations.py`,
`test_branch_execution.py`, and `test_branch_exclusions.py`; do not add another
multi-item workflow by default. Report new-case timing and get acceptance before
adding a heavy test. Record the mode/tool contract, blocker behavior, checks,
remaining limitations, and commit in the completion record.

## Implemented behavior and validation

Completed September 14, 2026. `execution_context.py` distinguishes interactive,
pre-authorization planning, authorized unattended work, and review without
changing the saved conversational UI flag. Initial, compact/recovery and resumed
worker policy retain the unattended completion and authority boundaries. Near-end
handling cannot finish an unattended item as a conversational answer.

Authorized workers get `report_blocker(question, inspected_evidence,
why_blocked)` rather than `ask_user`, plus scoped check-command requests. The
existing once-per-item repository reconsideration is preserved. A genuine
blocker stores evidence on the item and uses the existing waiting-for-user and
clean-independent-item scheduling path. New commands retain command approval.
Every worker response is checked against its exact offered tools before any
call executes; an unoffered mixed batch executes nothing and receives bounded
corrective feedback (two durable corrections, then a visible pause). Normal
interactive and proposal questions remain supported.

Validation: three new table/policy cases with no network/Git fixture, plus
existing chat (11 cases, 14.169s), answer recovery (14 cases, 22.273s), compacted
observations (2 cases, under 0.001s) and branch exclusions (6 cases, 3.436s).
The final 10-case T50/T51/T52 lightweight run passed in 0.006s. Root integration
validation owns the adapted branch-execution suite; a duplicate in-flight run
was stopped rather than repeated. No live trial was added. Genuine unresolved
scope or new authority can still pause, with evidence preserved.
