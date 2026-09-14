# Planner reliability and conversation workflow

September 14, 2026. Implementation branch: `work/planner-reliability`.

T62–T73 implement endpoint-bound planning, independent two-model routing,
credential-source preservation, persistent optional planner configuration,
legacy task/policy compatibility, complete final-check derivation, planner
accounting, specific stop explanations, persistent Plan, immediate Start,
responsive proposal dialogs, and a directly accessible Technical logs view.
T74 keeps each operation inside one owning cheapoS reply, with item-scoped
checks/reviews/commits, retained streaming Details, truthful historical model
identity, and explicit whitespace-only check wording.

## Focused evidence

- Access-policy cases: 9 passed in 0.009s; new cached routing case 0.001s.
- Existing routing/model-pool cases: 45/46 passed in 26.893s. The documented
  baseline unavailable-tool action-recovery failure remains (worker `a`
  instead of expected `b`). Its assertion was not weakened.
- Planner parser: 15 passed in 2.100s. New pure full-coverage parser case
  under 0.001s; thirteen unique checks now require repair instead of truncation.
- Planner configuration/accounting/transport/metrics/traces: 20 passed in 0.013s.
- Readiness: 6 passed in 0.004s. Preferences: 4 passed in 0.012s; existing
  fixture now explicitly includes the optional empty local planner field.
- Gateway credential regressions: 10 passed in 0.011s.
- Authorization: 8 passed in 0.017s. Existing planning HTTP: 11 passed in
  27.811s after allowing fixture loopback binding. The missing-runner baseline
  failure now passes and exposes the runner name.
- Existing Start cases: 3 passed in 14.885s. The existing setup scenario was
  extended with a deterministic setup interruption, then explicit saved-authority
  resume and consent recovery; final affected case passed in 6.530s. No new
  expensive workflow fixture was added.
- Final frontend selector: 130 tests passed in 99.217ms, plus JS syntax checks.
  Nine new conversation/render cases each took under 2ms.
- Specific pause cases: 9 passed in 0.005s; review validation: 7 in 0.003s.

These are measured focused runs, not a full-suite claim. No live inference,
paid-model request, benchmark, or personal task fixture was used.

## Browser evidence

One disposable synthetic HTTP fixture exercised real app rendering. Plan
content and expansion survived tab switches; approved scope survived reload;
keyboard navigation and the required tab order worked. Specific Chat failures
linked to Technical logs, whose equal-timestamp events appeared 3/2/1 while
saved chronology remained unchanged. Optional planner selection saved and
reopened successfully. Dialogs measured 1080px at a 1440px viewport, 976px at
1024px, and 366px at 390px, with 16px text and reachable controls.

Literal browser 200% zoom was not separately set; a 720 CSS-pixel equivalent
viewport was checked. A 52-event browser fixture verified an expanded older
entry stayed at the same viewport position when a new event arrived, and Return
to latest showed the newest entry. This caught and fixed native scroll anchoring
and control-insertion offsets. Card records retain the literal-zoom limitation.

T74 browser transitions passed for planner selection, waiting, streaming, plan
readiness, item-one commit into item-two work, specific pause, reload, and
merged outcome. One owning reply retained actual output and controls throughout.
Older authorized records missing their original plan show an explicit limitation
in Plan instead of presenting mutable scope as approved.

## Integration

Run startup uses the original authorization and journaled workspace creation.
A partial startup does not count as successful execution. Explicit retry or
reload/resume revalidates authorization, setup, and command consent; it cannot
create a second run. Changed models, endpoints, or grants still require the
existing authorization workflow. Direct-provider keys keep the existing
memory/environment policy; model configuration persistence does not persist keys.
