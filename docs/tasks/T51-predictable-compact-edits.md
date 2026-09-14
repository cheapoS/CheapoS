# T51 — Make successive compact edits predictable

Status: Not started
Priority: Medium
Depends on: current version-bound line editing
Size: S/M
Planning baseline: `4b6ed68`, September 14, 2026

## Outcome

When a model splits a change into small edits, every line range refers to file
evidence it actually received. A rejected stale edit tells the model exactly how
to continue, without duplicated blocks, guessed offsets, or asking the operator
to provide a file hash.

## Current evidence and files

Read [workspace.py](../../cheapos/workspace.py) (`replace_lines`),
[engine.py](../../cheapos/engine.py) (`request_versions`, `worker_file_tool`,
`edit_snapshot`, `LINE_EDIT`, `COMPACT_GUIDANCE`), and
[test_compact_edits.py](../../tests/test_compact_edits.py).

Important: the current engine already freezes file versions before inference.
`test_second_edit_in_same_response_cannot_use_shifted_line_numbers` already
checks that the first edit survives while the stale second edit is rejected,
then a later response succeeds using refreshed lines. Do not report the pasted
offset-corruption scenario as an unfixed fact without reproducing a different path.

## Work

1. Reuse that regression and inspect the trial's actual failing tool sequence if
   available. Distinguish a correctly rejected stale call from a wrongly applied
   edit, a model's later bad replacement, and an incomplete output. Record the
   result before changing editing semantics.
2. Keep the existing sequential contract: one mutation per canonical file per
   model response, then use the returned current-file evidence on the next
   response. Make the contract consistent across compact recovery, handoff,
   restart, and any exposed alternate mutation tools. Do not bind a queued edit
   to a newly computed hash merely because the first edit changed the file.
3. If same-file calls are rejected only incidentally through hash mismatch,
   provide specific feedback: the earlier call was saved, this call was not
   applied, and current numbered lines are supplied. Keep results for every tool
   call ID. A no-op first mutation or path alias must not make the contract vague.
4. Keep a bounded refreshed excerpt around the affected range, with total line
   count and incomplete-range information. A required excerpt outside that range
   remains readable. Preserve newline behavior, byte-based size checks, path
   boundaries, and legitimate insertions/deletions at EOF.
5. Teach the model to change one coherent region and consume the returned lines
   before continuing. Distinguish a syntax warning on saved work from an edit
   that was rejected. Do not clear failed verification or declare a partial
   architectural change complete just because a fragment parses.

## Out of scope

No general multi-edit transaction API, syntax-tree editor, larger global edit
caps, or fuzzy automatic offset correction. Those would need separate evidence
and a separate task. This card may finish with a small feedback improvement and
confirmation that the existing corruption guard already works.

## Acceptance

- The existing shifted-lines scenario remains protected; the final bytes match
  the intended sequential edits and contain no duplicated block.
- Same-file calls cannot adopt post-edit versions within the original response;
  independent files can still receive their own valid edits.
- The next model response receives accurate line evidence and can complete the
  change without operator input. Actual external edits still fail version checks.
- UTF-8 byte limits, CRLF, insertion/deletion, and existing path protections remain.
- Completion notes separate a reproduced defect from existing protection.

## Focused validation and handoff

Start with the selector plan. Reuse the existing compact-edit cases; add only a
small temporary-file or in-memory case for a demonstrated gap. Do not duplicate
the full recovery/handoff scenario. Report new-case timing and disclose any heavy
addition before implementation. Commit changes, update the task board, and record
what improved plus any remaining large-edit friction.
