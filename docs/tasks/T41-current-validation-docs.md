# T41 — Align current validation instructions

Status: Done
Depends on: none
Size: S

## Outcome

A model following the current docs chooses relevant checks and does not launch
a twenty-minute suite because an older task specification tells it to.

## Read first

- [Repository policy](../../AGENTS.md), [CONTRIBUTING](../../CONTRIBUTING.md).
- `scripts/check.py`, `scripts/dev_tests.py`, `scripts/parallel_tests.py`.
- [Exporter specification](../trials/unattended-run-report.md).
- [Test-performance record](../development/test-performance.md).

## Work

1. Correct CONTRIBUTING's two references to four default selector workers. The
   current implementation uses `min(8, os.cpu_count() or 1)`; document the actual
   behavior and `--jobs` override. Do not change concurrency to match stale prose.
2. Update the exporter specification's final integration section. Replace its
   mandatory full Python gate and historical 30-minute allowance with the
   formatter/HTTP checks, independent acceptance checks added by T42, and relevant
   frontend checks. Explicitly distinguish development selection from the exact
   verification commands captured in an approved cheapoS proposal.
3. Explain that a clean `check.py` invocation selects nothing. Use `--base` or
   `--files` when checking committed changes; do not report a clean selection as
   a tested feature. Existing evidence may be reused only when its candidate,
   command, and environment identities still match.
4. Keep old benchmark numbers labeled historical. Do not erase failed trial
   evidence or claim the entire suite now takes 46 seconds.

## Acceptance

- Current contribution and exporter instructions agree with the code and
  AGENTS.md. No unconditional full-suite gate remains in the active exporter spec.
- Examples use real entry points and explicit filenames. CheapOS launches argv
  directly; no shell glob, pipe, redirect, or chained command is proposed.
- UI/docs-only edits do not select Python regression tests. The policy still
  allows deliberate comprehensive validation when justified.
- This task changes documentation only. No runner, production safeguard, or
  application verification behavior is modified.

## Validation

Run `python3 -B scripts/check.py --plan` after edits, inspect local links and
command examples against the source, then run `git diff --check`. No runtime
suite or live model is needed for this documentation change. T42 supplies the
exact new acceptance-module names; leave them clearly proposed until it lands.

## Completion record

Behavior delivered: Updated CONTRIBUTING to the actual CPU-capped eight-worker
selector default and explicit --jobs override. Replaced the active exporter full
gate with focused implementation/frontend checks and visibly pending T42
acceptance commands. Distinguished development selection from approved argv and
identity-bound evidence reuse; retained historical measurements and failures.
Acceptance evidence: Compared docs to scripts/check.py (DEFAULT_JOBS, empty/UI/docs
selection), scripts/dev_tests.py (entry point, --directory/--pattern/--jobs and
repository imports), scripts/parallel_tests.py, and branch_evidence.bind_check.
All edits are Markdown; production behavior and runner policy are unchanged.
Commands and results: `python3 -B scripts/check.py --plan` selected zero Python
modules and only `git diff --check` for the four edited Markdown files.
`python3 -B scripts/check.py --files dist/branch_ui.js --plan` selected JS checks
and zero Python modules. Local Markdown links resolved; command flags and
existing JS filenames matched source. `git diff --check` passed. No runtime
tests were executed.
Remaining limitations: T42 must supply and validate the proposed independent
acceptance modules/commands and digest before T44 starts. The exporter feature
and its implementation test files do not exist yet. No new tests were added;
new regression runtime is zero. No runtime suite or live inference was run.

Update this card and the T41 status in TASKS.md; commit only scoped changes.
