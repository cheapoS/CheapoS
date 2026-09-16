# T87 — Make recovery continue the job with less micromanagement

Status: Done
Depends on: T84, T85; integrate T86 before final qualification
Size: M/L — deliver in ordered increments
Context: [DeepSeek Harness assessment](../development/deepseek-harness-assessment.md)

## Outcome

Ordinary tool failures, useful investigation, and reviewer corrections can lead
to the next useful action. “Continue” is an understandable control with visible
results; operators do not have to invent recovery incantations.

## Implementation

1. Map the current owners in `progress.py`, `work_policy.py`, engine recovery,
   `branch_worker_recovery.py`, reviewer recovery, transport, and coordinator
   dispatch. Use one decision owner per failure episode. Reuse existing recovery
   actions rather than adding another independent retry layer.
   List and retire the superseded dispatch decisions as each increment lands;
   a new policy object beside unchanged competing controllers does not finish
   this work. Preserve historical recovery records for diagnosis.
2. Keep a stable permitted tool set through ordinary work. Prefer edit guidance
   before replacing edit tools. A large file alone should not force compact edit
   mode; use demonstrated format/output failures and current route capability.
   Retain stale-file protection, complete-argument validation, and scope rules.
3. Distinguish newly obtained evidence from repetition. A new relevant source
   range, resolved uncertainty, or verified finding can support investigation
   progress; different timestamps, reworded prose, identical reads, toggling
   todos, and repeated unchanged passing tests cannot renew work indefinitely.
   Keep fingerprints and repeated-state detection separate from hard limits.
4. Prefer completing a coherent unit before review. A checkpoint interval should
   prompt an evidence-based status/next step when work is unfinished, without
   implying partial work is complete. Preserve actual operator-selected hard
   limits. Measurement/uncapped mode remains explicit, not a secret large cap.
5. Classify stops into retryable transport, implementation/tool failure,
   unresolved review finding, authorization/environment decision, or exhausted
   authorized allowance. For eligible failures, use the saved context to choose
   a local correction, accounted retry, eligible route handoff, or optional idle
   coordinator consultation. Record why that action was selected and its result.
6. Route “try again”/“continue” and the corresponding button through the same
   command path. Acknowledge immediately; dispatch only after durable admission.
   Continue an eligible saved action, or show the exact missing permission,
   environment repair, scope decision, or limit control. Do not silently reset
   billing/recovery allowances or dispatch duplicate tests on repeated clicks.

## Acceptance

- Useful exploration can reach an answer without making a cosmetic edit to prove
  progress; unchanged repeated reads still trigger the appropriate recovery.
- A review rejection resumes the existing repair with exact open findings; a
  passing unchanged test is reused only while all evidence identities match.
- Provider outages select only eligible authorized recovery and never cause a
  hidden paid request or replay of an executed mutation.
- Repeated Continue clicks are idempotent. A blocked command explains what must
  change and does not pretend the worker has restarted.
- Pause, spending/access rules, command permissions, independent review, and
  accepted plan boundaries retain their current force.

## Validation and handoff

Use table-driven policy cases, mocked providers, controlled promises/events, and
existing recovery/transport fixtures. Add no deliberate sleeps or new multi-item
agent runs. Record focused checks, timings, and one disposable UI continuation
flow. Commit each coherent increment; do not mark the card Done halfway through.

## Completion

Shared continuation policy selects repeated-evidence recovery and saved-stop
classification. Button and ordinary chat Continue use existing admission paths;
busy repeats are idempotent. Synthetic retry prompts and soft forced answers are
removed. New file ranges count as evidence; checklist churn does not. Large files
keep normal tools until a format/capability signal requires compact editing.
See [ownership and retired decisions](../development/continuation-ownership.md).

Four new pure/mock policy cases took 0.015s in the selected run (0.066s with cold
imports). Existing boundary, allowance, operator, progress and answer cases pass.
The existing worker-handoff integration passed in 9.309s; the existing three-item
execution module passed in 43.554s. Fixture expectations now acknowledge explicit
test consent and retained history instead of fresh messages. No new heavy fixture
was added. Browser Pause/Resume and final approval are recorded in T88.
