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

Status: Todo

- Behavior delivered: —
- Acceptance evidence: —
- Commands and results: —
- Browser scenarios and results: —
- Remaining limitations: —

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
