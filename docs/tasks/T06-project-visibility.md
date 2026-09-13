# T06 — Remove and reopen a project without deleting files

**Depends on:** T03. **Size:** M. **Result:** the sidebar can forget a project reference while keeping its repository and chats safe.

## Read first

`Engine.projects()`, `open_project()`, preferences persistence, project group rendering, task search, and selected-project localStorage handling.

## Problem

Projects are reconstructed from both `projects.json` and task sources. Deleting a path from the saved list alone makes it reappear on the next refresh.

## Implementation

1. Add a separate persisted hidden-project set keyed by normalized project identity. Apply it to normal project discovery, including projects inferred from existing tasks. Do not rewrite task source paths or delete `projects.json`.
2. Add a token-protected `POST /api/projects/hide` action accepting the selected known project identity. It hides the project and its chat group; it does not archive/trash its chats or change execution history.
3. Explicitly opening that existing repository clears the hidden marker and brings its existing chats back. Validate the actual repository through the existing open-project flow; do not create a second task copy on reopen.
4. Add `Remove from sidebar` to the project menu with one sentence explaining that files and chats are kept. If any task in that project is running or commit-pending, block removal with `Pause the running chat first` or the relevant commit recovery action. Do not silently hide live work.
5. On removal of the selected project, move to neutral home or another project and update stored selection safely. Add a small `Hidden projects` recovery view or route in Open project so reopening does not require remembering the entire path.
6. Search/history must make hidden-project results understandable without silently re-adding the project. Opening such a result should explicitly restore the project reference first.

## Acceptance

Remove, refresh, restart: the project stays hidden. Reopen: original chats return and no duplicate project/task is created. Test two projects with the same basename, missing/moved repositories, invalid paths, and a live task. Verify repository files/HEAD and all task data remain unchanged.

## Validation / limits

Add project discovery/hide/reopen API tests and a browser scenario. No project directory deletion, automatic path migration, clone/install flow, or hiding global demo state as though it were a real source repository.

## Completion record

Status: Done

- Behavior delivered: Persistent hidden-project identities, token-protected hide endpoint, explicit reopen, sidebar project menu, Hidden projects recovery, and labeled hidden-project search results with explicit reopen.
- Acceptance evidence: Hide/restart/reopen retains task records and repository HEAD; normalized full paths distinguish identical basenames; missing repositories remain hidden with actionable errors; active tasks/pending commits block removal.
- Commands and results: 3 project visibility tests, 28 HTTP tests, and 61 JavaScript tests passed; app syntax and diff checks passed.
- Browser scenarios and results: Remove project; reload keeps group absent; Open project exposes Hidden projects; explicit reopen returns original pinned/history entries. Recovery entries include full paths.
- Remaining limitations: Moved repositories require opening their current path; automatic path migration is out of scope.

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
