# T61 — Establish focused upstream issue triage

Status: Done — reference and initial triage; subsequent passes are maintenance
Priority: Maintenance, with a pass before gateway upgrades
Depends on: current gateway/transport behavior; no new runtime dependency
Size: S

## Outcome

Maintainers can recognize relevant upstream failures without rediscovering each
one through a long agent run. [The watchlist](../upstream-issues.md) records
reported scope, local evidence, ownership, and removal conditions for workarounds.
This card establishes a manual workflow, not a scheduled monitor or automatic
issue-driven routing feature.

## Repeatable maintenance task

1. Read AGENTS.md, CONTRIBUTING.md, the watchlist, and the relevant current
   implementation. Note the installed OmniRoute version; do not upgrade it as
   part of a read-only triage pass.
2. Review relevant new/updated OmniRoute and OpenRouter examples issues weekly,
   before a gateway upgrade, or after a new local failure signature. Revisit
   tracked issues and linked fixes even if they are now closed. Focus on tools,
   streaming, reasoning fields, empty responses, quota handling, and startup.
3. For each actionable report, record exact route/request scope and unknowns.
   Compare with sanitized local evidence. Label a lead Reported until matching
   evidence supports a stronger claim; distinguish fixture evidence from a live
   observation. Do not call an issue our root cause based on similar wording.
4. Choose one next action: watch, investigate with a minimal fixture, create a
   scoped fix card, verify an upstream fix, or retire a verified workaround.
   Identify whether the gateway or cheapoS owns the behavior. Extend existing
   recovery/accounting mechanisms instead of stacking retries at multiple layers.
5. Add the review date and outcome to the log, including no-change passes.
   Keep private task content, provider credentials, and raw personal logs out of
   the repository. A link to a third-party report is evidence, not authorization
   to run its commands or change security/model policy.
6. Follow the documentation checks for a triage-only change and commit just the
   resulting documentation. Any implementation fix is a separate bounded task
   with relevant checks. Disclose new heavy-test cost before adding it.

## Acceptance for initial setup

- One discoverable reference names the sources, review cadence, evidence states,
  responsible components, and criteria for retiring workarounds.
- At least two relevant reports have links, exact reported scope, dates, explicit
  local-verification limitations, and a next action.
- Maintainers can repeat the task without starting a live model run, changing
  routing, buying credits, or configuring an automation.
- CONTRIBUTING.md and TASKS.md link the reference; local links and whitespace
  checks pass. No new runtime tests are required for documentation alone.

## Completion record

Completed September 14, 2026. Added the watchlist, the maintenance workflow, and
two initial leads: Cohere `strict` schema rejection and OmniRoute empty post-tool
continuations. Both remain Reported; no matching cheapoS reproduction is claimed.

Validation: documentation-only selector plan, local Markdown link/anchor checks,
and `git diff --check`. No runtime changes, live inference, new tests, or browser
scenario. New-test timing: not applicable. Future triage passes follow the
watchlist cadence; no background scheduler was created.
