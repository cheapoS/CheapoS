# Continuation ownership after T84–T87

The Python harness remains the execution authority. This is an incremental
replacement of conflicting transitions, not adoption of a second agent runtime.

| Concern | Decision owner | Execution / retained safeguards |
| --- | --- | --- |
| Worker conversation transitions | `worker_conversation.continue_session` | Start/resume, review repair, route/coordinator handoff; item-separated archives, uncertain interrupted calls |
| Repeated evidence: continue, act, or answer | `continuation_policy.decide(..., repeated_evidence)` | Existing engine action/answer executors; hard allowances stay in their ledgers |
| Saved stop / ordinary Continue | `continuation_policy` | One existing Start/branch Resume path; admission saved before dispatch; running calls are idempotent |
| Stalled implementation eligible for branch handoff | `continuation_policy.implementation_handoff` | Existing `branch_worker_recovery` performs authority, scope, route and allowance checks |
| Transport retry inside one request | Existing provider/transport policy | Retry only that inference, account attempts; never replay tool execution |
| Reviewer provenance / reviewer transport | Existing reviewer recovery | Separate reviewer session and evidence identities; never use worker history as approval |
| Optional coordinator | Existing eligible consultation | Advisory continuation record, no new polling or allowance |
| Working memory | `working_state` | Optional advisory claims; exact directions overrule earlier next actions |
| Compaction | `context_compaction` | Exact active constraints, recent complete exchanges, task-local retrievable history |

Retired decisions: review-resume wholesale worker reset; post-commit and
reconciliation resets; competing handoff/coordinator history rebuilds;
large-file-only compact edit selection; forced answer on the penultimate soft
checkpoint turn; synthetic retry instructions that created a new request; and
engine-local repeated-evidence action selection. Legacy `refresh` remains a
transport-envelope repair used by the continuation adapter. Specialized routing,
permissions, evidence, and review controllers remain because their decisions are
not interchangeable with implementation progress.

New-range progress is recorded by path, content identity and line numbers.
Repeated ranges, todo toggles and repeated passing checks do not renew progress.
The records do not replenish hard work/spending allowances. An earlier approach
remains inspectable after a new direction, generation or commit, but its next
action no longer drives recovery. A worker may update the advisory record for
the current direction; doing so never verifies its steps.

History/output references currently live in the local task record and are excluded
from ordinary HTTP task responses. This favors safe recoverability over storage
size; a separate disk retention policy can be considered with measured task sizes.
No extra model requests are made for working memory or compaction. Genuine model
quality, throughput and provider-availability improvements require separately
selected live trials.
