# Worker conversation continuity

Worker history now survives small-edit recovery, model handoffs, checkpoint
intervals, saved verification, resume, and operator redirection. These transitions
append current saved evidence instead of replacing the conversation. Historical
file contents remain historical: refreshed version maps still prevent stale edits,
and passing checks/review remain bound to their existing evidence identities.

Operator and recovery directions are delivered when they change, rather than moved
or appended to the end on every request. Actual new operator messages still enter
chronologically. Token-capacity compaction remains available through
`fit_worker_context`; a context rejection still gets its existing bounded repair.
This change does not remove spending, command approval, or independent review.

On interrupted exchanges, missing tool results receive an explicit unknown-outcome
record. This does not execute the call or assert that it failed/succeeded. Invalid
historical JSON arguments are replaced with an empty object and annotated as
rejected, so preserving history does not resend invalid transport data.

Request metrics now include a `conversation` receipt at provider dispatch: a SHA-256
digest, message/assistant/tool-result counts, and serialized byte count. The receipt
contains no source text. It identifies the messages after engine-side policy
injection; it does not prove what an external gateway ultimately sent upstream.

## Investigation and validation (2026-09-15)

The installed OmniRoute Kiro translation source preserves assistant turns and tool
results, including explicit handling of orphan results. Local compression settings
were disabled, default mode off, and its compression analytics contained zero
receipts. This rules out no other upstream transformation: no production upstream
payload was captured and no live model completion was claimed for this branch.

Focused existing tests covered routing, operator controls/steering, checkpoint
boundaries, review workflow, retest recovery, malformed tools, compact edits,
branch operator/pause policies, and context/file observation behavior. The existing
malformed-edit/handoff scenario now asserts the earlier tool result survives and
still completes checks and independent review (1.124 seconds with the three new
pure continuity cases). Those three new cases alone measured below 0.001 seconds;
15 pure context/continuity cases together measured 0.011 seconds. No new heavyweight
workflow or full suite was added.

One existing branch-worker-recovery integration fixture fails at authorization
because it requests broad tests without full-suite approval. The identical failure
was reproduced on main before execution; its policy was not weakened here.

## Try the branch

Run the app from the feature worktree using a disposable profile. Try a small edit,
interrupt after an inspection, supply a correction, then continue. The next worker
request should retain the inspection and correction rather than reopen the task
from a summary. Verify its saved request receipts, focused checks, and independent
review. Compare repeated reads and completions with the previous run; do not treat
these deterministic regression tests as proof that every model will stop looping.
For an unattended live trial use explicit measurement mode and retain the selected
model/spending policy. The main checkout and running app were not restarted by
this change.
