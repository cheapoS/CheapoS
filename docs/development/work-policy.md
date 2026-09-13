# Focused worker policy

Small-edit mode is available before a failure when the selected output allowance is at most 768 tokens, or an observed file exceeds 200 lines / its excerpt exceeds 6,000 characters. An observed edit-output failure also enables it. These are explicit file/output signals, never model-name assumptions. Manual/local model selection stays fixed. The policy does not reduce output caps or send optional reasoning parameters.

Small-edit mode reuses the existing 80-line / 3,000-byte replacement contract and controller-held file hashes. Current numbered excerpts are supplied before inference; stale versions refresh instead of executing. Only one edit per file per returned batch is authorized against that version. New files use complete small chunks.

Orientation, implementation, verification and review supply concise stage guidance and prioritize the existing tools. No stage hides reads needed for missing context. Recovery now allows targeted reads too: a repeated unchanged read while recovering pauses through the existing observation/progress guard, rather than creating an unrestricted research loop. Reviews keep their full read-tool set and output allowance.

Completion still requires current verification, reviewer approval and a separate human commit decision. Stage names are controller hints, not completion claims. Project requirements and raw evidence remain governed by the T21 continuation contract.

The deterministic large-file A/B fixture produces the same two complete edits: reactive switching uses 6 requests and 1 malformed whole-edit failure; proactive switching uses 5 requests and 0 failures. Reads remain available and output allowance/model identity remain unchanged. This is a scripted control-flow comparison, not a live model benchmark. Observed signals reset with a new user request.
