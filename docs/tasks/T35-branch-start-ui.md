# T35 — Natural-language planning and a simple start flow

**Depends on:** T30, T33, T34. **Size:** M. **Result:** an operator can request a job from chat or a document, inspect one concise plan, and start the authorized branch run.

Read [BRANCH_RUNS.md](../../BRANCH_RUNS.md) and AGENTS.md first. Do not turn onboarding into a second settings dashboard.

## Read first

`dist/app.js` composer/project/task creation, `dist/guidance.js`, `LocalHandler` API contracts, coordinator request/routing code, readiness/presets, and T30's prepare/start endpoints.

## Implementation

1. Add a discoverable “Complete on a feature branch” choice near the composer. Normal chat remains the default. A chat request explicitly asking for a branch run may offer the same proposal inline; it must not silently start autonomous commits merely because a branch name appears in conversation.
2. Accept natural-language instructions and an optional readable local project document. Reuse constrained project-file access; no arbitrary filesystem picker path becomes authorized code execution. Capture the selected document contents/hash and plan revision so later document edits cannot silently change accepted work. A document supplied as context cannot grant command/merge authority. Markdown checkboxes are optional.
3. Add a bounded planner request using the selected eligible coordinator/worker route and existing provider/tool validation. Convert the request into T28's finite plan with titles, dependencies, criteria, check specifications, and final integration checks. Persist the original request and plan. Limit repair of malformed plans, report ambiguity, and reject silently truncated task lists. A model's branch/command recommendations are proposals for server validation.
4. Planning is visible and cancelable. Do not request inference just by opening the mode selector. When the operator requests a plan, use the displayed existing model/spending policy, reserve its usage, and retain that consumption in the draft/run ledger. Never use an unadvertised paid route to generate a free-run plan. Deterministic tests supply planner responses.
5. Show a compact editable proposal: task titles/criteria, selected project, committed base and proposed new feature branch, final target, placement, total budget/time, and test permission scope. Default the base to the selected integration target when available; do not silently start from another feature branch's HEAD. Show that existing uncommitted source edits are excluded. Advanced details may collapse, but the destination and authorization must remain visible.
6. Use one Start branch run button backed by T30. It authorizes the current revision and the displayed eligible tests/exact commands. Existing sufficient grants do not prompt again. Edits to the proposal invalidate its server token and prepare a fresh one before starting; avoid duplicate submission/runs on double-click or delayed responses.
7. Handle missing Git identity, unavailable independent free reviewer, unsupported repository configuration, existing branch name, stale base, and unavailable test environment with specific inline recovery. Preserve the draft and plan. Do not silently fall back to local heavy work, same-model review, or paid models.
8. Update new-mode help only for implemented behavior. Keep ordinary new chats, local-only manual chats, sample onboarding, and panel resizing functional. Do not duplicate provider settings, add account login, install software, or expose internal plan JSON as the main UI.

## Acceptance and validation

Browser-test an isolated fixture: enter a prose request and a project doc without checkboxes; inspect/edit the generated plan; start once; see the actual first item execute. Test keyboard navigation, narrow width, cancel, stale proposal, malformed planner response, and reload with an unsent draft. Confirm no Git mutation precedes Start and the source checkout stays unchanged afterward.

Run relevant JS/conversation, planner, routing, HTTP, and authorization tests. New static modules require HTML references and the server allowlist. No real model or private project as a UI fixture.

## Completion record

Status: Todo

Behavior delivered:

Acceptance evidence:

Commands and results:

Browser scenarios and results:

Remaining limitations:
