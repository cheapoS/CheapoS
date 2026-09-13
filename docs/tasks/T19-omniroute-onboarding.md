# T19 — Guided OmniRoute setup and return to CheapOS

**Depends on:** T18. **Size:** M. **Result:** an existing OmniRoute user can begin work without entering endpoint URLs or choosing two model IDs.

## Read first

T18 readiness contract, `startupMarkup`, `openConnections`, gateway actions, execution preferences, README companion setup, and current process ownership rules.

## Implementation

1. Build a short first-run flow: choose OmniRoute (recommended) or models on this computer; connect; open a project. Preserve advanced direct endpoints without making them required setup.
2. For a ready identified gateway, reuse it. For an installed stopped CLI, expose Connect/start with visible progress. For missing OmniRoute/Node, show a guided install explanation with accurate commands, copy actions, and a re-check button. Do not silently run a global install or require an embedded terminal for the first version.
3. If provider setup is needed, open the supported OmniRoute dashboard/setup route. State whether the user needs dashboard login, a provider credential, or an optional client key. Never collect provider keys in CheapOS merely to duplicate the dashboard.
4. While the setup flow is open, re-check readiness at a bounded interval or explicit return action, then return to CheapOS's next step. Do not create a permanent background watcher. Preserve completed steps after errors/reload.
5. Use current eligible free selection for role defaults; do not hardcode a stale model list. Check a distinct reviewer when coding needs it. Preserve an explicitly chosen existing pair.
6. Keep the model greeting brief and useful. The main success action is Open project/Continue chatting, not a settings screen. If the gateway fails, saved work remains accessible and local-only is a clear alternative chosen by the operator.

## Acceptance

Browser-test ready gateway with one configured provider: no endpoint or role/model-ID entry required. Test missing CLI, missing Node, login/key distinction, dashboard return, failed connection, retry, saved preferences, and existing working tasks. Setup should never trigger project work before the operator sends a request.

## Validation / limits

Use readiness/HTTP fixtures and mocked dashboard destinations for deterministic tests. Document remaining manual provider login/install steps honestly. Native installers, automatic upgrades, provider sign-up automation, and downloading local models are not part of this card. T20 completes local-only and sample-task paths.

## Completion record

Status: Todo

- Behavior delivered: —
- Acceptance evidence: —
- Commands and results: —
- Browser scenarios and results: —
- Remaining limitations: —

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
