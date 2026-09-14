# Deferred proposal: cheapoS in VS Code chat

**Status: documented for later consideration; implementation has not started.**
Discussed September 14, 2026. This note records the intended experience, initial
technical findings, and a proposed prototype. It is not an installation,
publishing, live-inference, or implementation request.

## Why consider it

Let someone open a project in VS Code, describe a job in chat, see cheapoS
coordinate implementation and review, and approve the resulting change in the
same editor. This could reduce onboarding and context switching while keeping
the existing browser application available.

The inspiration is [OmniCopilot](https://github.com/diegosouzapw/OmniCopilot).
Its [provider implementation](https://github.com/diegosouzapw/OmniCopilot/blob/main/src/provider.ts)
exposes OmniRoute models through VS Code's language-model provider interface and
forwards messages and tool definitions to the gateway. The host supplies the
agent workflow. Adding models to the picker alone does not introduce cheapoS's
worker/reviewer loop, task copies, evidence, or commit approvals.

## Recommended approach

Prototype a **`@cheapos` chat participant** backed by the existing local Python
engine. The [Chat Participant API](https://code.visualstudio.com/api/extension-guides/ai/chat)
lets an extension own the prompt/response interaction and supply progress,
response buttons, and follow-ups. This is a promising API fit, not a verified
extension or a promise that every browser interaction maps directly to chat.

| Component | Proposed responsibility |
| --- | --- |
| VS Code extension | Project context, chat, visible progress, task-copy diffs, and operator controls |
| cheapoS engine | Persistent tasks, worker/reviewer execution, checks, permissions, budgets, task copies, and commit/merge decisions |
| OmniRoute or another configured backend | Existing model access and routing under the selected access/spending policy |

The extension should call the engine; it should not implement a second worker
loop or let a host agent independently apply the same edits. Model credentials
remain with their existing owner. Installing OmniCopilot should not be required
for the extension to reach cheapoS's already-configured backend.

An MCP interface is a separate possible follow-up for assistants that want to
delegate jobs to cheapoS across editors. It serves a different interaction than
directly addressing `@cheapos`. See Microsoft's
[AI extensibility comparison](https://code.visualstudio.com/api/extension-guides/ai/ai-extensibility-overview).

## Existing integration points

The current [local server](../../cheapos/server.py) exposes task creation and
status, messages, steering, stop, command approval, permissions, commit preview,
commit decisions, and unattended branch actions. The
[browser client](../../dist/app.js) already polls task state for progress.
These are existing application endpoints, not yet a versioned extension API.
Re-read current code when resuming this proposal.

Use a small extension-host client to map chat sessions to persistent task IDs
and translate engine state into chat updates. Establish connection/version
handling and deduplication explicitly. The backend remains authoritative when
the browser and extension both observe a task.

The server currently validates localhost Host/Origin headers and a token for
mutations, and prohibits framing. Preserve those protections. Do not make an
embedded dashboard work by disabling its framing policy or broadly allowing
cross-origin requests; assess the extension-host API connection instead.

## First prototype, when authorized

Limit the first slice to desktop VS Code, one local Git project, one Interactive
task, and the existing scripted demo or deterministic provider. Connect to an
explicitly selected local cheapoS instance. Packaging, marketplace publication,
automatic engine installation, remote workspaces, and unattended UI parity can
follow separately.

Prove this interaction using disposable project data:

1. Address `@cheapos` with a small change request and bind it to the intended
   project and task. State which files the engine actually sees.
2. Show real worker actions, test output, reviewer feedback, and completion in
   chronological order. Identify the executing role/model and provide a way to
   inspect details; confirm the native chat presentation is usable.
3. Expose test consent and map cancellation to backend stop. The user must be
   able to request revisions after reviewer approval. Keep existing session
   grants and revocation behavior consistent across clients.
4. Open the diff for the exact reviewed task candidate. Send approval through
   the current commit flow; do not replace it with editor-side Git commands.
   A stale preview must refresh before the user approves a changed candidate.
5. Show the commit receipt and offer a follow-up. Reload/reconnect must recover
   the same saved task without duplicating dispatch, tool execution, or commits.

A later unattended slice must retain explicit Start authorization, durable
progress while the local engine is running, and the operator's final merge
decision. Closing the editor, ending a chat request, and choosing Pause need
distinct, documented behavior before unattended execution is offered there.

## Questions the prototype must resolve

- **Native chat fit:** Microsoft's overview describes participants under Ask
  mode. Verify supported VS Code versions, available modes, progress lifetime,
  detail rendering, approval buttons, and follow-up routing. Do not assume
  model-picker integration and participant integration have identical behavior.
- **Onboarding:** verify actual sign-in, extension, and subscription requirements
  for the chosen API/version before advertising account-free usage. A free
  extension does not make every configured model free.
- **Editor state:** decide how unsaved buffers, multi-root folders, branch
  changes, and simultaneous browser actions are presented. Never silently save
  buffers, snapshot a different project, or describe untested text as reviewed.
- **Lifecycle:** define engine discovery, token renewal, API compatibility,
  cancellation acknowledgement, reconnect deduplication, and task ownership.
  Ordinary chat cancellation must not leave invisible work running.
- **Workspace trust:** require appropriate project trust before dispatching
  executable work, while preserving cheapoS's command and commit authorization.
  Native editor consent must not silently grant broader backend permissions.

## Validation and decision to proceed

Begin with adapter cases using synthetic task events and mocked requests. Then
manually exercise one deterministic demo in an isolated data directory and
disposable repository through VS Code: request, progress, consent, review,
revision, commit, stop, and reconnect. A manual end-to-end scenario is evidence
for the prototype; do not add it to routine regression checks by default.

Follow [CONTRIBUTING](../../CONTRIBUTING.md): report measured timings, preserve
meaningful assertions, and disclose any proposed heavy test's cost before adding
it. No new tests or live model calls were introduced for this documentation.

Before building the complete extension, record what the prototype demonstrates,
which native chat limitations remain, whether it simplifies onboarding, and the
small implementation tasks needed next. Keep the browser app and its current
workflow usable throughout.
