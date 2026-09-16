# T88 — Demonstrate better completion and continuity

Status: Proposed — implementation/trials not started
Depends on: T84–T87
Size: M; live measurement is separately authorized
Context: [DeepSeek Harness assessment](../development/deepseek-harness-assessment.md)

## Outcome

Show whether the harness changes help tasks finish with less operator rescue,
while preserving required checks, review, and routing/spending authorization.
Do not use fewer pauses or a prettier activity view as a substitute for this.

## Deterministic acceptance

Reuse existing fixtures and small transcripts for these scenarios:

1. Explain a project, accept a user correction, and answer without edits.
2. Implement a bounded change, pass the relevant check, receive one actionable
   review finding, repair it, verify the changed candidate, and reach approval.
3. Resume from a transport failure after an edit/check has completed without
   repeating the mutation or unchanged verification.
4. Continue after compaction and restart with the same remaining work and latest
   guidance. Old review/check evidence cannot authorize a changed candidate.
5. Finish/commit under the existing approval contract and answer a follow-up
   referring to the completed work.

Use pure projection/policy tests for most combinations. Exercise existing
integration coverage once where state transitions require it. A new full workflow
test needs explicit runtime/frequency/cost disclosure and acceptance first.

## Browser acceptance

Use a disposable data directory and deterministic provider. Check prompt delivery,
working checklist, actual output, review feedback, Continue, Pause, and the final
operator decision in one conversation. Send and Enter must acknowledge promptly;
show queued/blocked/working honestly. Details stay open, tab return preserves the
expected scroll behavior, and stale spinners do not survive settled requests.
Do not use the operator's live task or permissions as test fixtures.

## Optional live comparison protocol

This card is not permission to spend credits, start background work, or change
model policy. Obtain the operator's selection of tasks/routes/budget first. Use
`measurement: true` for authorized live qualification. Select bounded tasks with
independent acceptance criteria and comparable initial repositories. Pin cheapoS
revision, model/provider identity, route policy, and prompts; report provider
outages and changing availability rather than attributing them to the harness.

Report completion/acceptance outcomes, worker/reviewer/model requests, repeated
reads/checks, recovery episodes, operator interventions, wall/active time,
reported tokens/cost, and uncertain usage. Include unsuccessful attempts. Label
assisted runs as assisted; never manually finish a feature and count it as an
unattended success. No percentage improvement claim from unlike models or tasks.

## Definition of done

Commit a report identifying exactly which deterministic and browser scenarios
passed, measured new-test cost, and remaining failures. If live comparison was
not authorized, record it as pending and make no live completion-rate claim.
Accept the milestone only on preserved correctness plus visible continuity;
defer further framework/plugin adoption until the results justify it.
