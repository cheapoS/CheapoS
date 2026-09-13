# T13 — Appropriate check timeouts and reusable verification evidence

**Depends on:** T09, T12. **Size:** L. **Result:** a selected full suite has time to finish, and passing evidence is reused only while its inputs still match.

## Read first

`Workspace.run_checks`, `Engine.checks`, `checkpoint`, `current_evidence`, `needs_patch_review`, commit preparation, T09 profiles, and `tests/test_review_workflow.py`/`test_check_output.py`/`test_commits.py`.

## Implementation

1. Add a bounded verification timeout associated with a recognized test profile or explicit user setting. Preserve legacy behavior for old tasks unless a clear migration is documented. For CheapOS's known full suite, configure sufficient time from T12's measurements rather than its current 90-second default.
2. Pass the selected timeout into run_checks and include it in check events. The effective deadline is capped by the task's remaining hard working-time envelope. Increasing a command timeout must not silently extend the whole task deadline or spending cap.
3. Distinguish `test assertion failed`, `test process timed out`, `task deadline reached`, `output limit`, and `user paused`. Show the relevant elapsed/allowed time and a useful next action; do not feed every infrastructure timeout back as a code defect.
4. Define one verification-evidence identity used by checkpoint and commit readiness: task workspace generation/baseline, relevant content/patch identity, exact normalized command, runner identity, and known dependency/configuration inputs. Never store arbitrary environment variables. If environment identity is uncertain after setup, invalidate conservatively.
5. Reuse a matching passing check through reviewer and final human approval. Explicit user rerun still executes. Code/test/config/dependency changes or reconciliation invalidate the appropriate evidence. Metadata/title/sidebar changes do not invalidate task checks.
6. Let the worker select a focused command from actual project guidance during repair, then the relevant regression command. Show which command passed; a focused check is not proof the entire repository suite passed.
7. A docs-only/no-executable-code task may have documented appropriate verification; do not invent a code-test success. Keep commit readiness and reviewer evidence honest.

## Acceptance

A scripted long check finishes under its approved profile deadline; cancellation and task deadline still stop its process group. An unchanged patch proceeds worker → reviewer → approval with one check, not three. Editing a test, changing the command/environment, or reconciling forces fresh evidence. A metadata rename does not. Old task/check records remain readable and are not automatically trusted beyond their known fields.

## Validation / limits

Add short deterministic timeout simulations and evidence invalidation tests, not a multi-minute sleep in every test. Run existing check-output, permissions, review, commit, and reconciliation coverage. No disabling subprocess bounds, hash comparisons, independent review, or human approval. Do not cache solely by filename or an assistant's claim that nothing changed.

## Completion record

Status: Todo

- Behavior delivered: —
- Acceptance evidence: —
- Commands and results: —
- Browser scenarios and results: —
- Remaining limitations: —

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
