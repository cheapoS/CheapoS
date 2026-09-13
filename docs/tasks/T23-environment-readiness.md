# T23 — Detect missing project tools and offer actionable setup

**Depends on:** T13, T21. **Size:** M. **Result:** an agent does not waste turns interpreting a missing runner/dependency as a code failure.

## Read first

Project brief from T21, task workspace lifecycle, command construction and environment filtering, T13 check failure types, snapshot omissions, and README's current manual dependency instructions.

## Implementation

1. Before dispatching a selected verification command, detect directly observable missing prerequisites: executable absent, selected environment absent, or a known test dependency unavailable. Keep detection cheap and bounded; do not import arbitrary project code just to inspect readiness.
2. Distinguish explicit evidence from inference. A manifest declaring pytest does not prove it is installed. A generic ImportError might be an implementation bug; preserve the traceback and avoid labeling all import failures as setup problems.
3. Present a CheapOS setup card naming what is missing, the affected task copy, and the proposed next step from actual project guidance. Include Open task copy/Copy setup command/Recheck where supported. Do not make users hunt through internal JSON for the workspace path.
4. Keep source/project environment and task-copy environment separate. Dependency directories are often omitted from snapshots. Never run setup in the source checkout just because it has familiar files.
5. Recheck after the operator prepares the task copy; invalidate relevant verification/environment evidence under T13 and resume the saved step. Avoid restarting the entire implementation.
6. Record setup-related state and useful diagnostics without credentials/environment dumps. Existing test grants do not authorize installation commands.

## Acceptance

Fixtures: missing executable, missing environment, genuinely missing declared dependency, a project-code ImportError, and readiness restored after setup. Each gets the correct explanation; repeated checks do not create an infinite loop. Source files stay untouched; successful setup invalidates stale evidence and preserves the patch.

## Validation / limits

Test readiness with fake executables/manifests and temporary environments. This first card provides detection and guided setup, not autonomous package installation. Do not use `run_checks` as an installer, copy unknown dependency directories into snapshots, or weaken environment filtering. Automated scoped dependency installation is a separately approved follow-up once this behavior is stable.

## Completion record

Status: Done

- Behavior delivered: Read-only prerequisite inspection before verification dispatch; structured missing-executable/environment/declared-pytest setup pause; visible task-copy path and source-attributed safe setup-command copy actions; explicit recheck and saved-verification resume. Recheck invalidates verification generation without discarding edits. No installation runs through test grants.
- Acceptance evidence: Fixtures cover absent executable/environment, isolated declared pytest absence, custom .pth uncertainty, project ImportError preservation, no repeated model dispatch while blocked, restored environment, unchanged source HEAD and preserved patch.
- Commands and results: 18 environment/verification/permission tests passed in 27.995s. HTTP recheck contract: 1 passed in 0.279s. Final environment tests: 4 passed in 3.802s. JavaScript syntax and diff whitespace checks passed.
- Browser scenarios and results: CUA disposable port 51030: setup card named missing .venv interpreter and task path; copied-command affordance cited README.md:2. Unresolved recheck stayed paused. Restored fixture interpreter enabled Resume saved verification, which ran one actual check and separate review, ending at human approval.
- Remaining limitations: No native Open Folder integration exists, so Copy task-copy path is offered. Dependency detection is deliberately narrow: an isolated declared pytest environment without custom .pth paths. Other dependencies remain unverified; generic ImportError output is not relabeled. Setup commands are copied only from recognized project guidance and run manually.

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
