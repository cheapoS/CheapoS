# Worker context management

Worker turns no longer compact at a fixed 60,000-character threshold.
Before dispatch, cheapoS considers the current route's non-stale gateway catalog
context_length, if available, including only metadata from the matching endpoint.
Catalog capacity is advertised metadata, not proof of the upstream configuration.

The input estimate includes messages and tool definitions. It starts with a
UTF-8 size estimate and calibrates against reported input-token usage and payload
sizes from the same endpoint/model. The output-token allowance and a 5% capacity
margin are reserved. These are estimates, not exact tokenizer counts. Usage and
spending authorization remain enforced separately.

When capacity is unknown, history is retained: no hidden fallback character cap
is applied. Context policy and estimates are recorded in task/request metadata
and policy changes in technical events. A recognized context-length rejection
allows one compacted retry; a second rejection propagates rather than looping.
Generic rate limits and malformed tool arguments do not trigger this retry.

At a known capacity boundary, the compacted target derives from the available
input token budget, preserving recent complete tool exchanges when space permits.
Findings remain unverified claims tied to the recorded patch/generation. Old
checks do not become current merely because their receipt survives compaction.
This policy governs worker size-triggered compaction; explicit recovery, model
handoff and task-transition context rebuilding still have their own semantics.

Handoff file snapshots preserve up to six distinct recently inspected ranges per
included large file rather than only the latest read. Files that fit are supplied
in full. Partial snapshots identify omitted evidence explicitly. Small edit
limits do not restrict reads: workers may read a whole small file. A reread that
recovers omitted known lines gets one recovery allowance per model/file version;
repeated identical inspections still retain their prior observation history.
