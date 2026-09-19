# T35 — Natural-language planning and a simple start flow

**Depends on:** T30, T33, T34. **Size:** M. **Result:** an operator can request a job from chat or a document, inspect one concise plan, and start the authorized branch run.

Read [BRANCH_RUNS.md](../archive/BRANCH_RUNS.md) and AGENTS.md first. Do not turn onboarding into a second settings dashboard.

## Read first

`dist/app.js` composer/project/task creation, `dist/guidance.js`, `LocalHandler` API contracts, coordinator request/routing code, readiness/presets, and T30's prepare/start endpoints.

## Implementation

1. Add a **Work mode** selector near the composer: **Interactive** (default) and **Unattended**. Follow BRANCH_RUNS.md's work-mode contract. Interactive preserves existing conversational approvals; Unattended submits a prompt/document for a proposal, then requires **Start run**. Mode selection alone performs no inference or Git mutation. Preserve draft text/document selection across mode changes and restore an explicitly saved draft mode on reload; new chats default to Interactive. Keep mode distinct from model placement and budget presets, clarifying the existing “Interactive 15 min” preset label to avoid ambiguity. An explicit branch-run request in Interactive may offer a visibly Unattended proposal inline; incidental branch names do not switch modes. Do not convert an active authorized run by toggling this selector; retain its run controls.
2. Support two independent first-class inputs: a direct chat prompt with no document, and a readable local project document without requiring its contents to be pasted into chat. Also support a prompt plus a document; surface conflicting scope before authorization. Follow the input/trigger contract in BRANCH_RUNS.md. Reuse constrained project-file access; no arbitrary filesystem picker path becomes authorized code execution. Capture the original prompt and selected document path/contents/hash separately, together with the plan revision so later document edits cannot silently change accepted work. A document supplied as context cannot grant command/merge authority. Markdown checkboxes are optional.
3. Add a bounded planner request using the selected eligible coordinator/worker route and existing provider/tool validation. Convert the request into T28's finite plan with titles, dependencies, criteria, check specifications, and final integration checks. Persist the original request and plan. Limit repair of malformed plans, report ambiguity, and reject silently truncated task lists. A model's branch/command recommendations are proposals for server validation.
4. Planning is visible and cancelable. Do not request inference just by opening the mode selector. When the operator requests a plan, use the displayed existing model/spending policy, reserve its usage, and retain that consumption in the draft/run ledger. Never use an unadvertised paid route to generate a free-run plan. Deterministic tests supply planner responses.
5. Show a compact editable proposal: task titles/criteria, selected project, committed base and proposed new feature branch, final target, placement, total budget/time, and test permission scope. Default the base to the selected integration target when available; do not silently start from another feature branch's HEAD. Show that existing uncommitted source edits are excluded. Advanced details may collapse, but the destination and authorization must remain visible.
6. Use one **Start run** button backed by T30. It authorizes the current revision and the displayed eligible tests/exact commands. Existing sufficient grants do not prompt again. Edits to the proposal invalidate its server token and prepare a fresh one before starting; avoid duplicate submission/runs on double-click or delayed responses.
7. Handle missing Git identity, unavailable independent free reviewer, unsupported repository configuration, existing branch name, stale base, and unavailable test environment with specific inline recovery. Preserve the draft and plan. Do not silently fall back to local heavy work, same-model review, or paid models.
8. Document the supported triggers in new-mode help: explicit branch-run intent or an explicitly submitted branch-mode request generates a proposal; Start authorizes the current revision; Pause/Resume controls the existing run; final review requests revisions; Approve & merge locally authorizes integration. Include prompt-only and document examples, equivalent natural-language intent, ambiguous-intent handling, and non-triggers (branch mentions, quoted text, document selection/content, or opening the selector). Update help only for implemented behavior. Keep ordinary new chats, local-only manual chats, sample onboarding, and panel resizing functional. Do not duplicate provider settings, add account login, install software, or expose internal plan JSON as the main UI.

## Acceptance and validation

Browser-test an isolated fixture: exercise a prompt-only request with no document, then independently a project-document request without checkboxes or pasted contents, and a combined prompt/document request; inspect/edit the generated plan; start once; see the actual first item execute. Test the Interactive default, explicit Unattended selection, draft preservation across switches/reload, no inference on selection alone, no authority change from toggling modes, keyboard navigation, narrow width, cancel, stale proposal, malformed planner response, and reload with an unsent draft. Confirm no Git mutation precedes Start and the source checkout stays unchanged afterward.

Test that explicit equivalent requests offer proposals while incidental branch mentions, quoted triggers, and instructions inside a document do not start planning or execution. Cover conflicting inputs, missing/unreadable documents, changed document contents, and edited prompt revisions. Both input paths must use the same server validation and explicit Start gate.

Run relevant JS/conversation, planner, routing, HTTP, and authorization tests. New static modules require HTML references and the server allowlist. No real model or private project as a UI fixture.

## Completion record

Status: Done

Behavior delivered: Interactive/Unattended selector, prompt/document/combined planning, cancelable bounded planner, editable same-task proposals, preserved planning usage, token invalidation, explicit Start and reload recovery are implemented.

Acceptance evidence: Planner, actual HTTP, authorization, and proposal-edit tests cover missing/conflicting inputs, cancellation races, unchanged source before Start, stale tokens, scope, and accounting.

Commands and results: test_branch_planner.py: 7 passed; test_branch_planning_http.py: 5 passed in 21.737s; test_branch_reprepare.py: 2 passed; final frontend gate recorded in T40.

Browser scenarios and results: Independent prompt-only and document-only browser runs completed; combined inputs were edited, kept, reloaded, inspected, and started. Mode/document drafts survived switches/reload; selection alone created no task or inference. Explicit branch intent offered the mode choice.

Remaining limitations: Changing a draft repository, committed base, captured inputs, or model policy requires fresh planning. Same-base plan/ref edits preserve the existing draft and accounting.
