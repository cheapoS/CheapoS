# Focused worker policy

Workers can submit coherent edits by default. `replace_lines`, `replace_text`,
`append_text`, and `write_file` remain available during implementation and edit
recovery. File size, an old error, or a small output allowance does not force
small-edit mode. The former 80-line / 3,000-byte edit limits and separate
24,000-byte creation limit are removed.

Malformed edit arguments trigger temporary guidance to retry a smaller complete
unit using current evidence. A successful mutation ends that guidance. Changing
worker, connection, item, baseline, or user request also clears it; Resume on the
same unresolved attempt retains it. Output truncation uses temporary retry
guidance too, and clears after a complete response. Historical attempts and usage
remain recorded. Reasoning adjustments apply only during the affected automatic
worker's recovery and only when its metadata advertises a supported control.

The existing resource ceilings remain: 256,000 UTF-8 bytes for a new file and
2,000,000 bytes for replacement input and the resulting edited file. These are
file-tool resource boundaries, separate from the operator's work and spending
limits. Workers should normally send a complete file or coherent replacement,
and split only when the provider cannot return it or a resource ceiling requires
it. Fully received valid edits are not rejected to enforce a preferred chunk size.

Line edits still use controller-held file versions from evidence delivered before
inference. Stale versions refresh instead of executing. Only one mutation per
canonical file per returned response is authorized; successful edits return fresh
numbered lines. Workspace restrictions, existing-file protection and syntax
rollback remain enforced.

Orientation, implementation, verification and review supply concise stage guidance and prioritize the existing tools. No stage hides reads needed for missing context. Recovery now allows targeted reads too: a repeated unchanged read while recovering pauses through the existing observation/progress guard, rather than creating an unrestricted research loop. Reviews keep their full read-tool set and output allowance.

Completion still requires current verification, reviewer approval and a separate human commit decision. Stage names are controller hints, not completion claims. Project requirements and raw evidence remain governed by the T21 continuation contract.

Deterministic cases cover complete rewrites beyond the former chunk limits,
verification and independent approval, temporary recovery after a malformed
response, and guidance expiration without resetting history or authority. These
are control-flow checks, not a live model benchmark.
