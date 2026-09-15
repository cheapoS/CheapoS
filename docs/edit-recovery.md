# Recovery from invalid line edits

A rejected `replace_lines` range returns the attempted range, current file length,
hash and numbered source near the attempted edit (the end of the file for an
out-of-bounds request). It makes no edit and does not ask the operator to supply
source code. The existing file-version and path checks remain enforced.

The task remembers the rejected edit and file version. An identical retry is
rejected before file-tool execution; corrected arguments or a new file version
can proceed. After two invalid ranges against the same file version, automatic
placement queues another eligible worker with the existing conversation and
repair evidence. Remaining tool calls in that response are closed without
execution. Existing model eligibility, review independence, spending and recovery
limits still apply. Manual placement does not silently change the chosen model.

Failed `run_checks` responses omit recognizable passing Node/unittest rows from
the worker-facing output, keeping failure diagnostics, assertion locations,
command, exit status and run ID. Original saved check evidence and operator
output remain unchanged and available through `read_check_output`. This does
not turn a failing check into a pass or authorize weakening an assertion.

Validation: six small filesystem/state tests passed in 0.003 seconds; nine
existing line-edit, version, sequential-edit and tool-feedback tests passed in
2.045 seconds. No inference, full suite, new agent/Git integration test or
real-time wait was added. The user's active task was not edited or restarted.
