# Structured check diagnostics

Configured, approved commands keep their original output and exit status. The
runner adds a versioned `diagnostics` index to the same saved check or command
receipt after capture. It does not install linters, change commands, infer success
from text, grant permission, or replace candidate/environment verification.

The initial adapters recognize these text formats:

| Reporter | Recognized form |
| --- | --- |
| TypeScript | `file(line,column): error TS1234: message` or `file:line:column - error TS1234: message` |
| Python type checker | `file:line[:column]: error/warning/note: message` with optional `  [rule]` |
| Ruff concise / Flake8 default | `file:line:column: F401 message` (severity remains unknown) |
| ESLint Unix formatter | `file:line:column: message [Error/rule]` or `[Warning/rule]` |
| pytest short summary | `FAILED/ERROR file::test - message` |
| unittest failure header | `FAIL/ERROR: test_name (qualified.owner)` |

Other versions, formatters, JSON, stack traces and passing-test rows may remain
unparsed. Recognized lines are not proof of reporter identity or complete error
coverage. Missing paths, line/column numbers and rule names remain null. Reporter
paths are untrusted text relative to the receipt's working directory; diagnostics
never resolve, read, execute or link those paths.

Each item carries path, line, column, rule/test name, severity, message, and a raw
reference with `run_id`, byte `offset` and exclusive `end_offset`. Offsets include
original ANSI bytes, UTF-8 and line endings. Text may be shortened explicitly.
The original log remains accessible through `read_check_output` and the existing
raw-output UI/download. Existing retention applies (eight logs, 64 MB each), so a
saved index can outlive its raw log; expiration remains an explicit read error.

Parsing examines at most the first 512,000 bytes, skips lines over 8,000 bytes,
and emits at most 80 items and 24,000 serialized item bytes. Each text field is
limited to 800 characters. `partial` / `limited` discloses capture, scanning,
line-size or item-budget limits. `unparsed` means no supported lines were found,
not that the command passed. No failure count is inferred from the index.

Worker command responses and saved review check records contain the index.
`read_check_output` also returns the original receipt's diagnostic index and
command/status/input bindings. Final-review reads still require the packet's
candidate-bound record digest. Resume and reuse preserve that receipt; stale
commands, directories, candidates and environments remain ineligible. General
setup commands remain command evidence and cannot satisfy verification.

Chat command details and the Tests view show an escaped diagnostic index beside
the original output. Old saved records without an index keep their existing UI.
No additional tools, prompt entry points or policy instructions are introduced.

Focused coverage lives in `test_check_diagnostics.py`, `test_check_output.py`, and
`test_check_diagnostics.js`, with existing verification, output filtering, receipt
and review tests covering the surrounding contracts.
