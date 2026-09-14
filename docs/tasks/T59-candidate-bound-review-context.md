# T59 — Let final review resolve missing context against the exact candidate

Status: Done
Priority: High — review accuracy
Depends on: T56, T57
Size: M
Planning baseline: `5a463b4`, September 14, 2026

## Outcome

A reviewer can inspect the relevant surrounding code before claiming that error
handling, a definition, or a required behavior is missing. Reading extra context
does not silently mark other chunks reviewed or permit approval of a different
candidate.

## Entry points and current limitation

Read [branch_final.py](../../cheapos/branch_final.py) (`build_manifest`, `_review`,
`final_check_review`), [branch_evidence.py](../../cheapos/branch_evidence.py), and
[branch_workspace.py](../../cheapos/branch_workspace.py).

Final evidence currently uses 20,000-character slices that can begin/end inside
a diff hunk or serialized receipt. Each request includes global requirements and
check summaries and warns against treating absent context as a defect. However,
the final reviewer only has `final_review_decision`; it cannot request the actual
surrounding source. Do not claim the existing instructions alone solve that gap.

## Work

1. Prefer coherent file/hunk boundaries when preparing bounded review packets.
   Include a compact location index and surrounding context for affected symbols;
   do not send the entire repository with every chunk or remove coverage guards
   to fit a packet. Preserve stable IDs/digests and exact coverage accounting.
2. Provide a bounded read-only context request for the final reviewer when the
   packet is insufficient. Bind every read to the manifest's exact candidate
   identity and path/range. Reuse existing safe file-read behavior where possible,
   but do not accidentally read a newer working copy or the user's source checkout.
3. Return provenance, line numbers, complete/truncated range information, and
   explicit unavailable-file results. Preserve path/symlink/secret boundaries.
   Reject stale candidate identity before the context influences approval.
4. Keep context requests distinct from decisions: account their model requests,
   bound repeated reads with existing recovery policy, and require a subsequent
   explicit final decision. Missing context must not become automatic APPROVE or
   an invented REQUEST_CHANGES defect. If needed evidence cannot be obtained,
   pause with that specific limitation rather than asserting the code is absent.
5. Read-only inspection grants no command execution, edits, provider change, or
   extra budget. T50 owns network-attempt accounting and T60 owns repeated-dispute
   handling; preserve their contracts at this boundary.
6. Carry verified context references into the final synthesis where relevant.
   Extra background is not proof that another assigned chunk was reviewed.
   All original requirements and required coverage must still be checked.

## Acceptance

- A scripted reviewer can find a `raise CLIError(...)` or helper immediately
  outside the original slice and cite the exact candidate lines.
- A genuinely missing behavior remains reportable as a defect with evidence.
- A read from a stale candidate or unsafe path fails without exposing content or
  expanding scope. A truncated excerpt is not labeled the complete file.
- Context reads do not count as approvals or expand chunk coverage. Explicit
  decisions and unchanged candidate/check identities remain required.
- Repeated identical context requests are bounded without a new broad retry loop.

## Focused validation and handoff

Start with the selector plan. Use a small source-text fixture and scripted context
requests for packet boundaries and coverage. Reuse one appropriate existing
candidate/Git identity case if the read source changes; do not duplicate full
finalization workflows. Measure new-case time and disclose any proposed heavy
test before adding it. Record context/coverage semantics, checked failure cases,
remaining uncertainty, and commit. No real model call is needed for this card.


## Completion record — September 14, 2026

Implementation: `e0fcc51` (with foundations `abe2545`, `226b604`, `3b48cef`).

Final chunks prefer file/hunk/line boundaries while retaining every character and digest. Packets include a file index; reviewers can request up to six bounded context ranges per packet from immutable Git blobs at the exact feature tip/tree. Reads validate literal path, regular-file mode, secret boundaries, range and candidate identity, and return provenance, numbered lines and truncation. Reads do not approve chunks or expand coverage. Identical reads and malformed responses consume bounded correction policy; an unavailable read can support a typed context blocker. Synthesis retains context references in chunk decisions.

Validation: three pure context/chunk/scripted-decision cases pass below 1ms each; the existing final readiness fixture now reads the actual immutable candidate and checks provenance. Two affected final/completion cases passed in 25.293s. No live inference. Very large single records/hunks may still require bounded splits; excerpts explicitly do not establish whole-file or other-chunk coverage.
