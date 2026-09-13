# Choose where the work runs

Use the execution button beside the chat spending limit, or open **Models → Execution**. This is a preference for **new chats**. Existing chats, including paused ones, keep their saved execution choice, task copy, and selected models.

| Choice | Conversation | Implementation | Review |
| --- | --- | --- | --- |
| Delegate heavy work | Installed local Ollama model | Free remote OmniRoute model | Different free remote model |
| All local | Installed local model | Same local model | Selected local reviewer, or the same model in a separate request |
| All remote | Free remote OmniRoute model | Same remote model | Different free remote model |
| Manual model pair | Configured worker | Configured worker | Configured reviewer |

Existing installations start in Manual mode to preserve their setup. For a laptop, choose **Delegate heavy work** and enter your installed model ID. This saves the preference without starting inference, downloading a model, or resuming a task. All local lets users with suitable hardware keep the entire workflow on their computer.

## Local chat delegates

The local assistant receives the latest message and a short conversation history. It has one tool: `delegate_work`. It does not receive repository contents, diffs, file tools, or verification tools. General conversation can end with a short answer; requests requiring project context are handed off to a remote worker.

Local chat is limited to one response per user message, at most 512 output tokens, with thinking disabled through Ollama's compatibility API. It goes idle after handing off work; it does not continuously poll or supervise the worker. CheapOS runs the controller. A follow-up returns to local chat, while an explicit resume continues the saved stage.

Local choices are checked against Ollama metadata before inference. Cloud aliases and models without advertised completion/tool support are rejected. Ollama can forward a localhost request to a cloud model, so a loopback URL alone does not prove local execution. See [Ollama cloud models](https://docs.ollama.com/cloud).

## Automatic free remote selection

Delegate and All remote use the OmniRoute endpoint and providers you have already configured. They only consider catalog entries with explicit zero input/output prices, advertised tool support, and no local or automatic/combo route. Eligible manually configured preferences are tried first, followed by the catalog's stable model order.

Before sending project context, CheapOS checks up to **four distinct candidates total** using a small `routing_ready` tool call with no repository data. The response must contain the expected call and token usage; that tool is never executed. Each probe has a 128-token output cap, a 30-second network timeout, and a 60-second stream limit checked between chunks. Probe tokens and cost are included in the chat's accounting.

Two different responding model IDs are required. The selected worker and reviewer are pinned to the chat. Failed probes can move to another free candidate; failed task requests pause without automatic retries. If no pair is available, CheapOS pauses with an explanation. It never substitutes local work or a paid route automatically. A reported charge stops work before returned tools execute. Catalog prices and a zero-dollar cap are not provider-side billing guarantees: inspect OmniRoute's own fallbacks and billing settings.

The interface records each handoff with both model names. File actions record the model that performed them. The reviewer receives the original requests, patch, verification output, and read-only tools. Command execution and reviewer takeover retain their approval steps.

## Keep a slow model from wandering

New runs default to:

- **12 worker turns between checkpoints:** a reminder two turns before the limit asks the worker to verify and wrap up. At the limit it pauses, preserving edits.
- **15 minutes per run:** approval waits do not count. Increase this under **Spending & limits → Advanced limits** for longer work, up to 12 hours.
- **Three identical reads without an intervening edit:** CheapOS pauses with the repeated-work explanation.
- Existing cumulative dollar, token, worker-turn, and iteration limits still apply.

The run timer is checked before inference, as stream chunks arrive, and before executing returned tools. A stalled network call can take its request timeout to return. Resuming starts a fresh progress window and preserves cumulative usage. A progress pause is not completion or approval.

Related edits can be batched in one model response. Context compaction retains the latest distinct reads, shortens large previews, and uses the saved diff instead of replaying full edit arguments.

## Activity shows evidence

**Activity** is a visible tab beside Chat. It shows current status, a pending command approval or resume action, all saved file changes, and check/review results for the latest user request. Checks or reviews for an older patch are labeled accordingly. Passing checks alone never imply reviewer approval.

A timeline lists recent actions newest first, including named files, failures, routing checks, and model handoffs. Open a file action to inspect the result or jump to its current diff. The complete technical event log stays collapsed underneath. Chat remains the place for conversation and live model output.

## Validation

Automated fixtures cover local-chat tool isolation, delegation through edit/check/review, different free model selection, failed and charged probes, local-only placement, persisted choices, follow-ups, and progress limits. They make no live inference requests. These tests establish controller behavior; live provider availability, coding quality, and cost savings require separate experiments.

A [live 31-second delegation smoke test](experiments/2026-09-13-delegation.md) also completed the full loop with Gemma, a free Cohere worker, and a different free Dots reviewer.
