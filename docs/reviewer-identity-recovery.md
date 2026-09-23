# Reviewer identity recovery

When a reviewer response fails the identity gate, automatic remote work tries unused, named, eligible routes on the authorized gateway. Each replacement must report an actual model identity and pass the existing worker/reviewer independence gate before its tools or approval are accepted. Spending and request accounting remain active.

Saved edits, check receipts and review context stay intact. Failed routes are persisted so a continuation after pause or restart does not replay the exhausted set. A successful replacement remains selected. Manual model choices require explicit replacement through **Choose reviewer**; that action lists eligible models and resumes a fresh review against saved work. Explicit selection can retry a previously failed route after the operator has repaired its connection.

Attempt exclusions are bound to the item candidate, final-review manifest, or
Interactive checkpoint evidence. A changed candidate can reconsider an eligible
reviewer without inheriting an unrelated item's failures. Earlier attempts stay
in scoped history, and revisiting that candidate restores its exclusions. Final
chunks and synthesis share one manifest scope. Provider cooldowns, qualification,
model authority and the actual-response independence gate remain in force.

For older saved item reviews, migration releases a route only when its recorded
non-probe requests all identify earlier candidates. Missing provenance and
current-candidate failures stay excluded. This does not discard reviews, reset
usage, change limits or manufacture approval.

Provider request schemas also differ. For Groq routes, the outgoing assistant
messages omit OpenRouter's `reasoning_details` extension, which Groq rejects.
Saved history, visible reasoning, tool-call IDs and evidence replies stay intact;
OpenRouter continuations keep their original metadata. This is a wire projection,
not a reset of the reviewer conversation or a change to response validation.
See the [Groq assistant-message schema](https://github.com/groq/groq-python/blob/main/src/groq/types/chat/chat_completion_assistant_message_param.py)
and [OpenRouter continuation guidance](https://openrouter.ai/openrouter/free/apps).

Unknown historical authorship is different: another reviewer cannot recreate a missing worker identity. The app reports this as an app-level provenance repair, retains the diagnostic evidence, and does not fabricate independence or silently waive the check. The existing narrowly scoped unchanged-committed-revision rule still applies.

Recovery dispatches use explicit route configurations, so they record their own
successful real responses in connection-scoped route health. This clears an
expired failure and allows subsequent exchanges to reuse the current capability
proof. A successful probe alone still cannot clear a real-request failure.

Validation uses deterministic recovery, identity, operator-action, transport and pause tests; no live model request or full test suite is needed for these regression cases.
