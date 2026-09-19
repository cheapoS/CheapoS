# Automatic Carto project context

Carto is enabled by default for projects. Adding or reopening a project schedules
local indexing in the background, including source capture and hashing; the Add
project request does not wait for it. Existing projects inherit the default on
their next context lookup. Explicit per-project off choices remain off. Change
the choice under **Project menu → Project context → Use Carto for this project**.

When the optional local parser is not installed, ordinary repository discovery
and file tools remain available. Install it from the cheapoS checkout:

```sh
python3 scripts/install_carto.py
```

The installer uses npm to install pinned Carto 2.1.5 and a private Node 22.22.0
runtime. It does not replace system Node. Native dependencies may require build
tools if a prebuilt binary is unavailable. No Carto CLI setup, hooks, generated
AGENTS.md, MCP server, or provider key is needed. Installation can be done while
the app is open; loading this cheapoS feature initially requires the updated app.

## Refresh behavior

Project registration or the first context request creates an index in the active cheapoS profile's
`carto/cache` directory. Each source repository or task worktree has its own
cache. Before serving context, cheapoS hashes permitted source files. Identical
content reuses the index; edits, additions, deletions and changed branch contents
trigger a background refresh. Carto reparses changed files incrementally.
Index writes run one at a time across projects and task copies. Repeated project
opens share a queued build and unchanged contents reuse the existing index.
There is no periodic scanning or continuous background model activity.
**Rebuild index** discards the cached database and recreates it. No timer-based
full reindex is necessary. During indexing or failure, agents continue with
ordinary file inspection; stale dependency results are not supplied.

Planning receives overview context and dependency context on file discovery.
Workers receive overview context when a working summary is built. Workers and
reviewers can call `get_project_context` with a relative `path`, a filename/symbol
`query`, or no arguments for an overview. Existing task conversations can use the
tool after project context is enabled. Turning it off stops future context lookups.

## Boundaries and limitations

This is advisory code navigation, not a correctness, review or permission gate.
The index runs locally without inference or network requests. Context supplied
to an agent goes to that agent's configured provider, just like normal file reads.
Repository content remains untrusted data. Existing workspace exclusions and
symlink restrictions apply. The index includes eligible `dist` and `tests` files,
which Carto's default scanner would omit. Non-source files, binary/invalid UTF-8
files, and individual sources above 1 MB are omitted; the existing workspace file
count limit and aggregate snapshot byte limit also apply. Large query results are
bounded and users can ask about a specific file or symbol.

The adapter uses Carto's SQLite import/symbol extraction, reverse dependencies,
and routes. Dynamic imports and some languages may be incomplete. We do not run
the full domain classification, generated architecture documents or AI analysis;
empty stack/domain/entry-point fields do not establish that the project has none.
Upstream risk labels are heuristic and never authorize or block work.

The cache contains a disposable copy of permitted source files, outside the
repository. Disabling preserves it; deleting the profile's `carto/cache` directory
removes it and the next enabled request rebuilds it. Settings live separately in
`carto/settings.json`.
Missing settings inherit the on default. Invalid or unreadable settings do not
silently re-enable a possible saved off choice; normal inspection remains usable.

## Validation

`tests/test_carto.py` uses temporary small files and mocked indexing, without
models, network, Git workflows or real-time waits. Automatic-mapping cases cover
default activation, saved opt-outs, deferred/coalesced capture, unchanged-cache
reuse, serialization, registration, and failure fallback.
A separate manual smoke with the real pinned runtime indexed three Python/JS
files in 0.051s and refreshed after deletion in 0.035s; it verified symbol lookup,
file dependencies and removal of stale reverse dependencies. This is not a
large-repository performance benchmark or evidence of improved model quality.
Live task qualification remains future work under the measurement-mode policy.

Upstream: https://github.com/theanshsonkar/carto
