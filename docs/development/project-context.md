# Project facts and continuation

Worker context includes a deterministic project brief and an evidence-backed continuation record. Delegate-mode coordinator messages remain separate and receive neither repository payload.

The brief uses permitted task-copy files only, through Workspace's listing/path/privacy rules. It reads at most twelve shallowest named guidance/manifest files, sixty lines and 1,000 characters each. Language hints cite a filename; entry points are candidates, not asserted runtime configuration. Test argv comes only from the task's configured command. Unknowns stay unknown. The serialized brief is capped at 24 KB. Excerpts explicitly point to read_file for omitted source.

Cache identity includes task-copy HEAD, workspace generation, permitted filenames, selected source hashes and configured test argv. Changes anywhere in a selected manifest/guidance file invalidate it, including beyond the excerpt. No cache survives solely by project path. Context is deterministic and stored with the task's normal saves; original events remain intact.

Continuation retains all user requests and ordered steering corrections, with newest conflicting direction taking precedence. It does not infer semantic completion from assistant prose. At most eight changed/observed files supply fresh numbered thirty-line/1,000-character excerpts and complete-file hashes; checks/reviews retain their evidence identities. Existing compact-edit version tracking still controls writes. Raw evidence remains in saved task history; source remainder is available through read_file. The record is bounded at 112 KB. More than 48 KB of serialized user requirements and steering causes an explicit pause requesting a focused task, rather than losing requirements.

Deterministic repeated-question fixture: a legacy action summary needed one additional guidance read to recover the configured test command; the new summary needs zero. This measures provided context, not live model behavior or quality. Fixture brief: 1,044 bytes; continuation: under 1 KB. No embeddings, paid summaries, or extra model calls are used.
