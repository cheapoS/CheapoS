# T01 — Persistent task metadata and lifecycle API foundation

**Depends on:** none. **Size:** M. **Result:** sidebar metadata survives reloads and live worker saves, without changing task execution data.

## Read first

`cheapos/storage.py` (`Store.get`, `save`, `publish`, `list`), `cheapos/server.py` (`public_task`, bootstrap/tasks endpoints), `cheapos/engine.py` (`Runtime`, `start`, `event`), and `tests/test_http.py`.

## Problem

The app has no durable rename/pin/archive model. Adding fields to a copied task and saving it can race with a worker's newer events, or be overwritten by the worker's next save.

## Implementation

1. Add a separate UI-metadata record per known task, preferably `tasks/<id>/metadata.json`, using existing atomic JSON persistence. Keep raw task execution records compatible. Use a dedicated lock/atomic update for metadata.
2. Define defaults: `custom_title=null`, `pinned=false`, `archived_at=null`, `trashed_at=null`. Missing metadata means an ordinary active-list task. Validate types, reject unknown mutation fields, and tolerate a malformed metadata file without losing the task.
3. Add `POST /api/tasks/<id>/metadata` accepting only `custom_title`, `pinned`, and `archived`. `custom_title` is a trimmed nonempty string up to 120 Unicode characters, or null to reset. `archived` maps to a timestamp or null. Reject control characters; titles remain plain text. Validate the task ID by resolving an existing task, never by trusting a path from the request.
4. Present effective title and metadata consistently in bootstrap, task listings, and full-task responses. Preserve the original prompt/title in execution history; do not rewrite requests or reviewer evidence. Introduce one shared presentation function if needed rather than three competing serializers.
5. Add `GET /api/tasks?view=active|archived|trash`; omitted view means active. Apply filters to user-facing listings, not internal recovery/accounting enumeration. Reserve trash behavior for T04.
6. Renaming/pinning a running task is allowed. Archiving requires no live runtime thread and no pending commit transaction; use an actionable rejection. Do not implement an automatic stop in this card.
7. Archived tasks remain readable but cannot start/continue until restored. Enforce this in controller entry points, not only button visibility. Restoring changes metadata only; it does not start inference.

## Acceptance

- Old task JSON loads unchanged and appears in the active list.
- Rename while a scripted worker publishes and saves events: both the new title and all worker events survive reload/restart.
- Pin/archive persist; repeating the same request is idempotent.
- Archived tasks are absent from default bootstrap/listing and present in archived listing; full-task inspection works.
- Empty/oversized/invalid titles, unknown keys, missing IDs, and missing request token fail without touching task data.
- Archive while running or commit-pending is rejected; restore never dispatches work.

## Validation / limits

Add `tests/test_task_metadata.py` for persistence and concurrent-save behavior; add focused HTTP coverage for the new routes and all response shapes. Run existing chat/commit tests relevant to serialization. No sidebar redesign, automatic naming, Trash deletion, provider calls, or `.cheapos/` migration that rewrites every task on startup.

## Completion record

Status: Todo

- Behavior delivered: —
- Acceptance evidence: —
- Commands and results: —
- Browser scenarios and results: —
- Remaining limitations: —

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
