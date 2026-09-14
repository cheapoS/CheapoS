# T45 — Verify the download and report the real outcome

Status: Done (two incomplete outcomes documented; browser acceptance pending complete feature)
Depends on: T44 attempted; feature acceptance needs a complete candidate
Size: M

## Outcome

Determine whether the report feature actually works for the operator. Retain
failed attempts and distinguish app approval from independently observed success.

## Work

1. Inspect T44's exact candidate, receipts, app/source revisions, test-pack hashes,
   and saved checks. Confirm the independent checks ran on this candidate and
   the worker did not alter them. Reuse matching recorded evidence rather than
   repeat valid passing checks merely for this handoff.
2. Run an isolated UI server with synthetic saved records. With computer use,
   exercise Export report on paused and completed Unattended runs; inspect the
   downloaded bytes. Include a partial historical record if supported.
3. Verify keyboard access, truthful outcome/usage text, and that Interactive chat
   does not show an inapplicable export control. Preserve the composer draft and
   Details expansion. Export must create no model request, check, commit, merge,
   resume, or task-state mutation. Compare counters/records around the action.
4. Record a browser failure as a failure, not a screenshot success. If tools or a
   complete candidate are unavailable, leave that acceptance pending and state why.
   Do not use the user's personal task history as a substitute fixture.
5. Add a dated report under `docs/trials/` with a compact sanitized machine-readable
   summary if useful. Include pair/access basis, exact versions, request/token
   totals with uncertainty, provider/check elapsed times, commit receipts, tested
   acceptance, planning assistance, and interventions after Start.

## Acceptance

- Successful qualification requires the real download and independent feature
  requirements to pass. App readiness alone never makes this a feature pass.
- For incomplete T44 work, retain the failure, affected criterion, saved candidate
  identifier, and next concrete correction. The reporting card may be Done while
  the feature stays Blocked; those statuses must be explicit.
- Do not infer a benchmark success rate from mixed models/versions/retries.
  Included access and estimated zero cost are not provider invoices.
- Leave the feature branch unmerged/unpushed. Present a clear ready-for-integration
  result or an honest incomplete result for the operator.
- Reuse disposable UI tools for this focused scenario. No new slow browser harness,
  heavy regression, or full-suite gate is introduced.

## Validation

Check report links, accidental private data, and `git diff --check`. This card
does not require repeating Python/Node regressions unless a repair changes tested
behavior. Report any newly necessary heavy test to the operator and obtain
acceptance of the extra cost before introducing it.

## Completion record

Feature qualification: incomplete in both live attempts
Browser scenarios and actual download evidence: unavailable; neither candidate has the endpoint/UI
Evidence/report paths: [dated qualification record](../trials/exporter-20260913/RESULTS.md)
Interventions and limitations: planning assisted; zero execution interventions. No complete feature or browser qualification.

Update this card and TASKS.md. Commit only sanitized records and scoped repairs,
not generated personal reports, downloaded artifacts, or credentials.

Attempt 1: [qualification record](../trials/exporter-20260913/RESULTS.md). Incomplete feature; no browser success claimed.
