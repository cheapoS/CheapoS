# Scoped local code search

`search` finds case-insensitive literal matches, one result per matching line.
Query-only calls remain valid. All calls now return an object with `matches`
instead of the old bare list that silently stopped at 60 results.

```json
{"query":"review_decision","path":"cheapos","glob":"*.py","limit":20,"context_lines":2}
```

- `path` defaults to `.` and accepts an existing workspace-relative file or
  directory. A directory includes its descendants, not similarly named siblings.
- `glob` is optional, case-sensitive Python `fnmatch` over the **whole**
  workspace-relative POSIX filename. `*` can include `/`: `*.py` matches Python
  files at any depth and `src/*.py` includes nested source files. `**` has no
  special directory semantics; `**/*.py` requires a slash. Patterns do not
  expand the eligible inventory. Absolute paths, traversal and backslashes are
  rejected. Brackets and `?` follow `fnmatch` semantics.
- `limit` is an integer from 1 to 60, default 60. A page also stops before
  exceeding 20,000 characters in its serialized `matches` array (Unicode JSON,
  not a byte or whole-envelope limit).
- `context_lines` is an integer from 0 to 5, default 0, on **each** side of a
  match. Context stays in that file and may overlap another match's context.
- `query` contains 1–200 characters without NUL or newline. It is not a regex
  or a multiline search. Booleans, out-of-range numbers and malformed cursors
  are rejected, not coerced or silently clamped.

Each match has `path`, one-based `line`, `text`, and `text_truncated`. Optional
`context_before` and `context_after` contain numbered text entries with the same
truncation flag. Each text entry contains at most its first 300 characters. A
match can occur after that excerpt; `text_truncated: true` requires a numbered
`read_file` call to inspect the full line. This also supplies full source evidence
for reviewers; discovery results do not create an approval or a source citation.

The response reports `returned`, `total_matches`, `offset`, `has_more`,
`truncated`, `next_cursor`, `files_searched`, `skipped_files`, `skip_reasons`, and
`snapshot`. `truncated` describes remaining matching lines, while each text entry
separately reports clipping. Skipped files are not evidence of absence.
`total_matches` counts eligible readable text only. At the last page `has_more`
and `truncated` are false and `next_cursor` is null.

To continue, repeat the exact query, filters, page limit and context size with
`cursor` set to the preceding `next_cursor`. Treat it as an opaque continuation,
not an offset to edit. Results sort by path, then line number. The cursor binds
parameters, workspace identity, scoped inventory and the bytes of every readable
file in that scope, including files without a match. Changed sources, parameters,
additions, removals and renames reject the old cursor with an instruction to
restart without it. Identical source bytes remain reusable after Resume. Changes
outside the scope do not invalidate it. A cursor is neither permission nor proof
that previously read evidence is still correct.

Search uses Git's tracked/untracked, nonignored inventory, even with an explicit
directory. Tracked files remain discoverable if a later ignore rule matches them.
Existing secret/dependency exclusions and path validation remain in force;
symlink files and symlink parents are never searched. Unlike `list_files` with
an explicit directory, search does not include ignored build output. Binary,
invalid UTF-8, unreadable and oversized text files are skipped with counts and
reason categories. The existing 2 MB per-file ceiling still applies.

Search does not inherit the file-list display cap. It rejects scopes over 5,000
eligible files or 100 MB of readable text and asks for narrower filters instead
of returning misleading partial coverage. It scans the selected scope on every
page to validate source hashes and count matches; it holds only one file and one
page of results at a time. File-stat and inventory checks detect ordinary edits
during the scan, but this is not an atomic filesystem snapshot against concurrent
writers. There is no LSP, regex engine, persisted index or live inference involved.

## Consumer and runtime audit

- `tools.dispatch_file_tool`, worker/checkpoint review, item review and read-only
  discussion pass the structured response through their existing JSON tool
  receipts. No runtime caller indexes the old list.
- `test_large_file_tools` was the direct Python list consumer and now selects
  `result['matches']`. Third-party direct Python consumers must do the same.
- `READ_TOOLS` supplies the single search schema to worker, Interactive,
  Unattended and reviewer inventories; discussion selects it from worker tools.
  Work-policy filtering retains it for read-only questions. Decision-only
  coaching and durable final review do not gain an unavailable search tool.
- Existing observations, context retention and event rendering serialize
  arbitrary tool results. Saved old list receipts remain historical data and
  are not rewritten or presented as complete searches.
- The catalog's current tool contract explains continuation, stale-source
  recovery and completeness limits only when search is offered. Request
  assembly refreshes that contract once without changing grants or history.

`test_search` uses temporary files, a fake inventory for most cases, one tiny Git
inventory fixture with no commits, and existing in-memory request/review harnesses.
It covers more than 60 matches, filters, continuation, output/context bounds,
invalid inputs, ignored files, symlinks, skipped files, source changes and
provider-boundary correction/Resume/handoff. The actual item-review entry point
consumes pages before a separate validated decision. No model or network calls,
real-time waits or full multi-item workflows are added.
