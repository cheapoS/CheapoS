# T22 — Proactive small edits and stage-appropriate work

**Depends on:** T21. **Size:** M. **Result:** weaker models get a clear small next action and the tools needed to complete it without generating giant malformed edits.

## Read first

WORKER/CHAT/REVIEW instructions and tool schemas, compact-edit recovery, file-version tracking, output-cap recovery, checkpoint submission, and compact/tool-argument/answer tests.

## Implementation

1. Make the existing small-edit path available proactively for large files/responses or models with observed edit-output failures. Base thresholds on explicit size/capability signals, not model-name stereotypes. Preserve the operator's manual/local model choice.
2. Keep edits complete and bounded. The controller supplies current numbered excerpts and tracks file versions. The model supplies only the requested replacement. On mismatch, return refreshed evidence; never ask the operator to copy hashes.
3. Use a small deterministic stage policy for context/tools: orientation, implementation, verification, review. Reuse current tool sets and keep a route to ask for missing context. Do not hide necessary read tools in a way that forces a guess or recreates the earlier repeated-read dead end.
4. Keep concise working instructions: satisfy the full request, reuse existing structures, make the smallest sufficient diff, avoid speculative abstractions, do not repeat entire files in prose, and report real evidence. This adopts the useful terse-output/minimal-code principles without installing a persona skill.
5. Preserve enough output allowance for valid calls. Adjust optional reasoning only through verified supported controls and the established task policy; unsupported settings should not break normal calls. Do not globally disable reasoning for review or shrink caps until JSON truncates.
6. Distinguish completion from an intermediate edit. Only current verification/review and the operator's final decision complete delivery.

## Acceptance

Fixtures cover a large replacement split into valid pieces, a small ordinary edit, stale line evidence, two edits touching the same file, malformed output, missing context, and a complex reviewer request. No partial call executes. All original requirements and test coverage remain. Compare wasted reads/tool failures with the same scripted scenario before/after.

## Validation / limits

Run compact-edit, output-recovery, tool-argument, and review tests. Browser-check one named-model handoff and small-edit stream if presentation changes. No minified production code for token savings, giant prompt rewrite, automatic paid upgrade, or removal of necessary validations/tests.

## Completion record

Status: Todo

- Behavior delivered: —
- Acceptance evidence: —
- Commands and results: —
- Browser scenarios and results: —
- Remaining limitations: —

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
