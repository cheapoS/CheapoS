# T67 — Preserve complete final verification during plan repair

Status: Ready
Priority: P2 — verification coverage
Depends on: current plan parser
Size: S
Planning baseline: `db774c7`, September 14, 2026

## Outcome and reproduced failure

Schema normalization may fill safe omissions, but it must not silently reduce
the job's verification requirements to make a plan validate.

When `final_checks` is absent, `_parse` collects item commands, deduplicates
them, and takes `[:12]`. A thirteen-item fixture with thirteen unique check
commands produced only twelve final checks. Later changes can invalidate earlier
work; per-item checks do not replace complete final integration coverage.

## Read first

[branch_planner.py](../../cheapos/branch_planner.py) (`TOOLS`, `SYSTEM`, `_parse`),
[branch_runs.py](../../cheapos/branch_runs.py) (schema and check limits),
[branch_final.py](../../cheapos/branch_final.py), and
[test_branch_planner.py](../../tests/test_branch_planner.py).

## Implementation work

1. Keep deterministic deduplication when every required final command fits.
   Never clip the list or omit later items silently.
2. If missing final checks cannot be derived within the existing schema, use
   the bounded planner-repair path to request explicit consolidated integration
   commands that cover the complete job. Do not simply raise global schema or
   execution limits, invent a shell chain, or run all commands via a new bypass.
3. Preserve explicit user-supplied check requirements. Any consolidation must
   retain their semantics and be visible in the proposal before Start.
4. Inspect the new check-command examples in the planner prompt: CheapOS's
   `scripts/check.py --plan` prints a selection and does not execute tests.
   Do not present it as proof of behavioral verification. `git diff --check`
   can check whitespace where appropriate, not replace requested feature tests.
5. Maintain limits binding, executable validation, safe tool parsing, and bounded
   repair. Failure to form a complete proposal must produce an actionable
   planning response rather than a partially authorized run.

## Acceptance and focused validation

- A thirteen-unique-command plan cannot silently become a twelve-command final
  contract. It receives repair feedback or an explicit valid complete plan.
- Duplicate commands are deduplicated without dropping unique coverage; valid
  explicit final checks and the operator's limits are retained.
- Planner guidance distinguishes command discovery from actual verification.
- Use parser-only synthetic proposals and fake repair responses. No commands,
  model calls, or multi-item Git fixtures need execute. Time new cases and reuse
  relevant existing parser tests. Update TASKS.md and this card before commit.

## Completion record

Pending.
