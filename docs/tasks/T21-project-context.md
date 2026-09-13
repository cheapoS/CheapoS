# T21 — Compact project brief and durable continuation state

**Depends on:** none. **Size:** M. **Result:** a worker starts with relevant project facts and can continue after a handoff without re-reading everything.

## Read first

`Engine.initial_messages`, `action_messages`, context compaction, `routing.coordinator_messages`, file-version evidence, snapshot exclusions, and answer/compact/chat recovery tests.

## Implementation

1. Define a compact project brief from permitted project files and existing observations: language(s), entry points, repository instructions, known test commands, relevant dependency manifests, and where each fact came from. Mark unknowns instead of inventing commands or framework versions.
2. Generate it deterministically where feasible. Cache it against the task baseline and relevant manifest/guidance changes, not forever by project path. Do not scan dependency directories or files excluded by the snapshot/privacy policy.
3. Add a bounded continuation record: current user request, remaining requirements, next step, completed file/check/review evidence, unresolved failures, and current file versions. Use existing saved events as evidence; do not treat an assistant claim as a completed edit/check.
4. At a handoff/recovery, send that record plus the necessary current excerpts. Retain original user requests and raw evidence locally. Omitted/truncated material must be labeled and retrievable through existing tools; preserve the newest corrections and all active requirements.
5. Keep local coordinator context small and separate. Delegate-mode local chat must not receive repository files or regain edit/check tools because a project brief was added.
6. Document invalidation rules and payload bounds. Do not replace exact edit/version evidence with a lossy narrative summary. Keep prompt construction stable where possible to avoid needless cache-prefix changes.

## Acceptance

Repeat a project question/follow-up and recover a worker after interruption: the model gets current facts and does not need to rediscover the test command. Manifest changes invalidate the relevant brief. Conflicting later user guidance wins while older still-active requirements remain. File hashes/line numbers are current after edits, handoff, and compaction. Secret/ignored content and coordinator isolation remain protected.

## Validation / limits

Add deterministic context-construction tests, serialized-size checks, and a before/after fixture of repeated reads. Do not introduce embeddings, a vector database, paid summarization, MCP dependencies, unlimited history, or a new general memory service. A useful cached brief is enough for this card.

## Completion record

Status: Todo

- Behavior delivered: —
- Acceptance evidence: —
- Commands and results: —
- Browser scenarios and results: —
- Remaining limitations: —

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
