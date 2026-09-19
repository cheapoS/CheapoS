# Project discovery across repositories

Planners and workers share `cheapos/project_discovery.py` for repository facts.
Discovery reads permitted local files; it does not execute package scripts,
import configuration, install dependencies, fetch preview URLs, or authenticate
to services. Declarations describe conventions, not command authority.

## What the map provides

- Component directories with the actual paths of guidance, manifests, READMEs
  and lockfiles. A root README does not automatically identify the active app.
- Root and nested guidance in the initial context, ordered ahead of README
  content at the same depth. Guidance is associated with its directory subtree.
- Manifest locations for Python, JavaScript, Rust, Go, Ruby, PHP, JVM, .NET,
  CMake, Deno, Elixir, Swift and Dart projects. Recognition identifies evidence
  to inspect; it does not assume a framework or invent verification commands.
- Declared validation/build scripts from complete `package.json` excerpts,
  including the source field, working directory, and any package manager named
  by metadata or adjacent lockfiles. Script bodies remain unverified. Other
  ecosystems use the same manifest/document inspection path; their executable
  configs are never evaluated during discovery.
- Plain file discovery for static sites, unfamiliar languages and repositories
  with no recognized manifest. These are not treated as unsupported projects.

The planner selects the relevant component using the request and inspected
evidence. It proposes meaningful checks following that repository's conventions;
the harness no longer prescribes cheapoS's own test paths, Python/JavaScript
split, or an arbitrary two-second verification target.

## Summary windows are not work limits

The initial planner map is at most 96 KB, including up to 500 permitted file
paths, 32 component summaries, 12 source excerpts (100 lines / 4,000 characters
each), and 24 declared scripts. Excerpts, omitted counts and continuation
guidance make these windows explicit. The existing workspace inventory and
file-size boundaries still apply.

`inspect_project_file` lists directory entries in pages of 60. Pass its
`next_entry_offset` back as `entry_offset` to continue. Directory inspection
also returns a map scoped to that directory, allowing access to components
omitted from the initial summary. File reads retain line/column continuation
and literal query support. A URL passed as a file path receives a specific
correction with existing local path choices.

Workers receive the same component classification and source ordering within
their existing 24 KB brief. Their explicitly selected verification command is
preserved. None of these summary windows stops work or renews spending limits.

## Proposal errors versus missing setup

A missing executable in a model-invented command is not enough evidence of an
environment problem. For example, `Run the identified test command` goes through
proposal correction and, with automatic planner selection, the existing eligible
planner handoff. It does not become an operator-facing missing `Run` dependency.

A command copied from the direct request, selected document or inspected source,
or a runner declared by package-manager metadata, can establish a real missing
setup requirement. Provenance never authorizes execution. Normal exact-command,
scope, model/spending and approval checks still apply. Discovery cannot establish
that arbitrary commands are safe, that dependencies are installed, or that tests
pass.

Existing planning conversations upgrade to the new initial map and planner
instructions when resumed. They retain request history, evidence, failed reads,
attempt counters and usage. A planner handoff can inspect again rather than
inheriting a forced-proposal tool choice from a previous failed inspection.

## Next step: prepare context when a project is added

The existing optional [Carto integration](carto-context.md) already supplies
symbol/import/dependency context to planners, workers and reviewers. Today it
starts indexing on the first context lookup (or through Project context
settings), rather than automatically when a project is registered.

A follow-up should prepare these two complementary sources on project addition:

1. Save the deterministic repository map and its source-file identities in the
   local app profile. It identifies components, guidance and validation
   declarations, including files that a code-symbol index does not cover.
2. Queue Carto indexing in the background when installed and enabled for the
   project. Return the Add project response immediately; source capture/hashing
   must also run outside the HTTP request path.
3. Show compact context status (available, mapping, unavailable) as information,
   never a task-start gate. Agents can inspect files while indexing proceeds.
4. Refresh after relevant file/branch changes. Match results to the actual task
   copy's content identity, not merely the source project or current main branch.
   Keep separate indexes for divergent task copies; do not serve stale facts.

Carto helps locate symbols and affected tests; it does not decide which nested
application the user intends, establish that a script is safe, or validate a
model's proposal. Keep both kinds of context available and retain ordinary file
inspection as the fallback. This onboarding/cache lifecycle is a follow-up design;
the current change builds discovery at planning/brief time and preserves the
existing optional Carto integration.

## Regression checks

`python3 -B -m unittest tests.test_project_discovery -v` uses small local files
and scripted model replies. Git inventory is substituted; no inference calls,
network requests, live tasks, sleeps or full branch workflows are introduced.
Fixtures cover nested applications, Python, mixed-language repositories, static
and unknown layouts, permissions/exclusions, pagination, missing-runner
provenance, automatic planner handoff and saved-conversation upgrades.
