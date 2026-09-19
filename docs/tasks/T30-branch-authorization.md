# T30 — One run authorization and scoped test permissions

**Depends on:** T28, T29. **Size:** M. **Result:** the operator can authorize a concrete branch-run contract once without granting unlimited execution or changing manual chats.

Read [BRANCH_RUNS.md](../archive/BRANCH_RUNS.md) and AGENTS.md first. T35 owns the polished UI; this card supplies the server contract and fixtures.

## Read first

`LocalHandler.trusted/do_POST`, `Engine.approve_check/session_permissions`, `ProjectTestGrants`, `test_profiles.py`, work limits/presets, and existing preview/approval HTTP tests.

## Implementation

1. Add prepare/start-authorize endpoints or equivalent explicit task actions. Preparation is read-only with respect to source Git and execution. Return a short-lived proposal ID and the exact plan revision/digest, project/base/target/feature ref, model policy, total limits, required checks, and supported permission proposals. Proposed API names are new contracts; document the chosen names.
2. Starting requires an explicit operator decision through the existing same-origin/token-protected API. Resolve proposal IDs server-side and reject stale/expired proposals or changed plan/base/project/branch availability. Do not accept model-supplied `approved`, branch-ownership, or arbitrary grant IDs as authority. Idempotency must prevent a double-click from creating two runs/branches.
3. Persist the bounded run authorization contract separately from ephemeral proposal tokens and command grants. Its scope is local reviewed commits to the owned feature ref for the approved work. Manual chats keep per-patch human commit approval. The model-facing prompt must explain the active mode accurately; it never receives a general Git tool.
4. Register T29 workspaces through the controller's trusted mapping. Extend registration only as necessary, preserving source/copy replacement and configuration checks. Combine the start action with explicit consent to supported project-session unittest profiles and/or exact final-check commands shown in the proposal. Do not broaden the matcher to arbitrary executable prefixes, pytest, npm, installation, or shell syntax.
5. Reuse existing valid grants without asking again. Ordinary edits to test files within scope do not cancel a profile grant. Changed runner/configuration, a different project, revocation, or restart requires revalidation/new consent. If the actual workspace fingerprint cannot be prepared before start, bind consent to the projected committed inputs and verify the materialized fingerprint before granting; a mismatch requires a fresh decision.
6. Revoke automatic continuation independently of retaining saved work. Pausing stops execution; leaving/revoking the run prevents later automatic commits until explicitly resumed/authorized as appropriate. A final merge needs a separate final approval; neither the initial contract nor a reviewer can grant it.
7. Keep authority changes explicit. In-scope repair and reviewer revisions need no new plan approval. Added requirements, different destinations, paid placement, larger limits, or broader command scope require an operator amendment tied to a new plan revision. An operator's submitted revision can serve as the explicit action when all unchanged scope is clear; do not add a redundant confirmation for every correction.

## Acceptance and validation

Test valid start, missing/forged/stale proposal, double submission, plan tampering, cross-project replay, protected destination, and revoked authorization. Grant tests once and run multiple supported selectors without another prompt; changed executable/config and restart must not reuse the grant.

Confirm source changes do not occur before authorization and ordinary manual commits still require their preview approval. Use isolated HTTP fixtures and relevant existing permission tests. No live credentials or new provider integration.

## Completion record

Status: Done

Behavior delivered: `/api/branch-runs/prepare`, protected `/api/tasks/<id>/branch-start`, and `branch-leave` actions; five-minute server-held proposals bound to captured plan/inputs, private workspace, project/base/ref, model policy, limits and concrete check scope. Authority is durable; command grants are session-only.

Acceptance evidence: Explicit decisions, expiry, tampering and cross-task replay rejection; idempotent Start; unchanged dirty source/index; exact/profile command grants; restart expiry and revoked authority; manual action guards. Preparation materializes only a private copy and runs no checks or models.

Commands and results: `test_branch_authorization.py` 8 PASS; `test_branch_start.py` 3 PASS (12.840s); `test_branch_http.py` 5 PASS (13.496s).

Browser scenarios and results: UI coverage belongs to T35; API authorization must be tested here.

Remaining limitations: Execution is connected in T33 and the UI in T35. This card authorizes then pauses. Scope-changing work requires a fresh proposal; later revision controls retain the same rule. Missing verification setup saves an inspectable blocked draft.
