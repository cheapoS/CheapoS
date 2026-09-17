# Repository workflow

After completing and validating changes, commit your work before handing the project back. cheapoS workers also commit to this repository, and unrelated uncommitted changes can block their commit flow.

Stage only the changes you made for the current task. Preserve any unrelated user or worker changes; do not include, discard, or overwrite them just to make the working tree clean. If they prevent completion, explain what remains.

Tell the operator when changes are committed. The operator handles app reloads
with the restart button; do not restart cheapoS automatically unless asked.

# Validation while iterating

Follow the current change-scoped policy in CONTRIBUTING.md. Start with
`python3 -B scripts/check.py --plan` and run the relevant checks. UI-only and
documentation-only changes do not require the full Python suite. A routine merge
is not a reason to repeat unchanged passing checks. Historical task cards that
say to run every test before every integration do not override this policy.
Use the full suite only for an explicit comprehensive check, a release, or broad
backend risk that focused tests cannot cover; explain that choice. Preserve
meaningful assertions and product verification/permission safeguards.

Prefer available Carto context for architecture, symbol discovery, and dependency impact before broad file searches. Verify findings against the current source. If Carto is unavailable or indexing, continue with normal inspection without blocking work.

## New test cost must be visible

Do not introduce new slow/heavy regression tests as part of routine work. Prefer
small deterministic cases and reuse existing integration coverage. A new full
multi-item agent/Git workflow, deliberate real-time wait, expensive repeated
fixture, or material increase to the normal selected checks needs explicit cost
disclosure before it is added. Tell the operator what the test covers, its
measured or estimated runtime, how often it will run, and why cheaper coverage
is insufficient. Keep it proposed until the operator accepts that extra cost.
Unknown runtime is not permission to call a test fast; measure the smallest
representative fixture first. Include new-test timing in the completion report.
Do not weaken assertions or product verification/permission rules for speed.

# Live unattended trial policy

Use explicit measurement mode for future live qualification/feature trials so
arbitrary cumulative work caps and check deadlines do not censor the baseline.
Set `measurement: true` on planning requests (or `plan.measurement: true` for an
operator-prepared proposal). Keep the authorized model/spending policy, including
free-only placement when selected. Track all usage, failures and interventions;
do not substitute huge numeric caps or silently renew a failed run's allowance.
Choose future bounded defaults from comparable measured runs, not guesses.
