# T08 — A pure, explicit unittest command-profile matcher

**Depends on:** none. **Size:** M. **Result:** a tested parser can distinguish ordinary variants of an approved test runner from unrelated commands. It grants no permissions yet.

## Read first

`Engine.verification_argv`, command parsing/shell-syntax handling, `Workspace.run_checks`, `tests/test_permissions.py`, `tests/test_syntax_guard.py`, and compact-command recovery tests.

## Proposed implementation

Create a small `cheapos/test_profiles.py` module with a pure matching layer. Inputs are a validated argv, the task workspace, and a concrete approved profile. Output is matched/not matched plus a concise structured reason. Parsing must never execute the candidate command.

A first profile contains: schema version, runner=`unittest`, resolved Python executable identity, the fixed `-m unittest` entry point, permitted test roots inside the task copy, supported selector/flag forms, and the project identity supplied by the controller. Keep schema and sample objects documented in the module/card completion record.

Support deliberately:

- An approved Python executable, optional `-B`, then `-m unittest`.
- Explicit `discover` with `-s`, `-p`, and `-t` values validated against approved roots and the workspace. Restrict top-level import roots to the approved project boundary.
- Dotted test-module/class/method selectors whose files resolve inside approved test roots.
- A small enumerated set of runner flags such as `-v`, `-q`, `-f`, `-b`. Unknown options return no match and fall back to ordinary approval.

Resolve relative roots in the task copy. Detect path escape and symlink escape. Do not treat all `python` paths as the same executable, or reorder arbitrary argv. Quote handling belongs to the existing command-to-argv parser; never execute a shell to normalize it. A glob passed to unittest is an argument, not permission to run shell expansion.

## Acceptance matrix

Match: the approved discovery command; another test pattern within the approved roots; another test module under those roots; a permitted verbosity change. No match: `python -c`, a Python script, `-m pip`, another executable, a shell chain, a different runner, an outside root/top-level, unknown flags, missing values, NUL/invalid input, traversal, and symlink escape.

Different modules within the scope execute different repository code; the profile is not a security sandbox. Its scope will be explicitly approved in T10.

## Validation / limits

Add `tests/test_test_profiles.py` with table-driven positive/negative examples and temp-path cases. No changes to existing authorization outcomes in this card. No pytest/npm support yet, dependency install, code-content classifier, shell prefix wildcard, or network calls. Keep exact-command approval as a separate supported path.

## Completion record

Status: Todo

- Behavior delivered: —
- Acceptance evidence: —
- Commands and results: —
- Browser scenarios and results: —
- Remaining limitations: —

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
