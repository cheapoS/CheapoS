# T91 — Explicit settings scopes and safe chat changes

Status: **designed, not implemented**. This card is ready for an implementation
agent. Canonical product/behavior contract:
[Settings that make their scope obvious](../design/settings-system.md).
Screen study: [settings-preview.html](../design/settings-preview.html).

## Outcome

An operator knows whether a change affects this chat, future chats in a project,
or future chats throughout the app. Saving cannot accidentally affect another
scope. Approved tasks retain their setup; a legitimate task-specific change can
continue the remaining work without a magic chat message.

Read [AGENTS.md](../../AGENTS.md), [CONTRIBUTING.md](../../CONTRIBUTING.md) and
[AUTONOMOUS_WORKFLOW.md](../../AUTONOMOUS_WORKFLOW.md). This card supersedes T89's
ambiguous `operator`/`user` scope wording, not its existing independence or consent
requirements. Preserve `98401b1`'s saved-run-policy invariant.

## Ordered implementation slices

Commit and validate each slice; do not turn the entire spec into one giant edit.

### 1. Defaults storage and resolver

- Implement a small authoritative defaults store with app values, project
  overrides, schema version and revision checks. Use existing validation and
  canonical project identities. Keep credentials and grants in their own stores.
- Define absent/inherit versus explicit Automatic, false and zero. Preserve all
  legacy model bindings/pins, coordinator choices and limits during migration.
- Return resolved values with provenance. Add compatibility adapters for current
  preferences/config/role-mapping callers; avoid independent dual-write systems.
- Validate affected inherited project combinations when app defaults change.
- Acceptance: pure resolver and migration cases prove precedence, removal,
  explicit values, legacy pins and rejection without partial writes.

### 2. Capture the setup once for each new chat

- Route draft creation, Interactive creation and unattended planning through the
  same resolver. Capture resolved settings/source revisions before model requests.
- Bind plan approval to the displayed setup revision. Keep already authorized
  run policy, current connection validation and existing task authority intact.
- Existing tasks display saved fields; do not backfill from current defaults.
- Acceptance: changes to defaults cannot invalidate or rewrite either of two
  saved chats, including one paused at final review. Reuse existing real-Git
  authorization coverage rather than adding another full workflow fixture.

### 3. Split the current mixed settings form

- Replace mixed `executionPreferences()` saves with named This chat, Project
  defaults and New chat defaults destinations, using one form draft per scope.
- Add clear entry points and headers; composer opens **Chat setup** for its exact
  task ID, captured when opened. Project menu opens project defaults explicitly.
- Shared form sections: Agents / Spending & work / Permissions. Scoped buttons
  say where they save. No implicit “also save as defaults” checkbox.
- Apply model/limit links to the right section and scope. Remove ambiguous
  `User-selected`, `Operator-selected`, and generic `Save settings` labels here.
- No chained writes across scopes, swallowed save failures, or loss of dirty
  forms on scope switches. Opening/saving does not make model calls.
- Acceptance: browser flow demonstrates each destination, accurate source labels,
  errors, keyboard behavior, narrow layout, and switching selected chat mid-edit.

### 4. Task changes continue the correct work

- Implement the task settings adapter with allowlisted changes, capability
  reporting, expected revision and durable idempotency. Reuse existing authorized
  limit/coordinator/reviewer operations; do not mutate arbitrary task fields.
- Paused chat offers **Apply & continue** and secondary **Apply without
  continuing**. Preserve cumulative usage, exact scope, command grants, edits,
  valid checks, worker identity and findings. Continue its unfinished phase.
- For active work, implement **Pause, apply & continue** only through a durable
  safe-boundary operation. Until supported, use the explicitly limited **Pause
  to apply** flow and retain the draft; never advertise a fake successful apply.
- Do not change workflow/placement with a generic patch after work has started.
- Acceptance: paused final review changes reviewer and continues review, not
  implementation; duplicate submission applies once; a failed apply retains all
  old authority; a saved change plus dispatch failure reports those separately.

### 5. Connections, limits and remaining settings

- Organize existing connection UI under **Shared connections**, show named
  connection impact, and preserve active-task guards and revocation behavior.
- Separate free/paid spending from bounded/uncapped work. Retain legacy advanced
  authority flags without silently unifying their different meanings.
- Permissions shows actual scope and opens existing grant/revoke workflows.
  Keep browser appearance and installation sharing separate from work defaults.
- Start with Automatic and Use only this model. Add Prefer a model only with a
  tested runtime contract covering every supported role/phase; do not weaken pins.
- Acceptance: free-only remains free-only under uncapped work; new model choices
  cannot silently authorize paid access or tests; coordinator remains on demand.

### 6. Focused qualification and handoff

- Exercise the acceptance table in the spec with small deterministic cases.
  Include offline/restart persistence, stale revisions, scope navigation and
  saved-task compatibility. Use fake time and scripted providers; no live calls.
- Run `python3 -B scripts/check.py --plan`, inspect the selection and run relevant
  checks. Preserve existing authorization and meaningful browser coverage.
- Do not add slow multi-item workflows or real waits without first disclosing
  measured/estimated cost and obtaining acceptance under AGENTS.md. Measure and
  report the runtime of newly added tests. Docs/prototype changes alone do not
  need the Python application suite.
- Update user documentation with the scope model. Report unsupported transitions
  accurately. Commit only this work and tell the operator; they handle reloads.

## Implementation map

Start from these existing owners; verify names against the implementation checkout:

| Responsibility | Existing code |
| --- | --- |
| Current mixed form, limit dialog, composer links | `dist/app.js`: `executionPreferences`, `chatLimits`, `coordinatorSettings` |
| Current app and project defaults | `cheapos/engine.py`: `preferences`, `save_preferences`, `configure`, `save_role_mappings`; `cheapos/role_mappings.py` |
| Execution capture and local assistance config | `cheapos/routing.py`: `setup_task`, `execution_from`, `coordinator_assistance_config` |
| Saved plan authority and task revisions | `cheapos/branch_controller.py`, `cheapos/branch_operator.py`, `cheapos/engine.py`: `update_limits` |
| Connection identity/access | `cheapos/connections.py`, `cheapos/access_policy.py`, `cheapos/server.py` |
| Existing display preferences | `dist/panels.js` and display-specific controls |
| HTTP boundary | `cheapos/server.py`; existing trusted mutation mechanism |

## Hand this to the implementation agent

> Implement docs/tasks/T91-settings-system.md using the canonical design in
> docs/design/settings-system.md. Work in its ordered slices and preserve saved
> task authority. Prioritize fixing mixed settings scopes and cross-chat effects.
> Do not redesign the execution engine, broaden paid access, remove verification
> safeguards, or interpret a pinned model as an automatic preference. The preview
> is a design study, not production JavaScript to paste into the app. Validate
> each slice with scoped deterministic checks, commit your own changes, and report
> completed slices, remaining limitations and test timing for review.
