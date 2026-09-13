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

Delegate and All remote use the OmniRoute endpoint and providers you have already configured. They only consider catalog entries with explicit zero input/output prices, advertised tool support, and no local or automatic/combo route. Eligible manually configured preferences are tried first. Then selection prefers models that have returned usable responses in that role, fewer recent failures, and observed latency. Advertised reasoning and context capacity break reviewer ties. These are compatibility signals, not measured coding-quality scores; model size and words such as ‘pro’ or ‘mini’ do not determine quality.

Before sending project context, CheapOS checks up to **four distinct candidates for the worker** using a small `routing_ready` tool call with no repository data. The response must contain the expected call and token usage; that tool is never executed. Each probe has an output cap of up to 1,024 tokens (or the chat's lower limit), a 30-second network timeout, and a 60-second stream limit checked between chunks. Probe tokens and cost are included in the chat's accounting.

A working worker can answer questions and inspect files immediately. At the first edit checkpoint, CheapOS checks up to **four other candidates for review**, requiring a different responding model ID. Each successful selection remains in use while it is eligible and responding. If no reviewer is available, changes and the checkpoint request are saved; Resume retries reviewer selection and verification without repeating worker edits. A new follow-up message replaces that pending request. Model check failures appear in Chat and Activity.

Failed probes move to another free candidate. For transient HTTP failures, connection failures, broken response JSON, incomplete streams, or calls to tools not offered in that step, an automatic remote chat can hand off to a different free model, at most twice per run across worker and reviewer. Each replacement selection checks up to four candidates, excludes failed models from this run, and keeps the other role distinct. The same saved conversation and tool results go to the replacement; failed responses never execute partial tool calls. Existing worker-turn, checkpoint-turn, time, dollar, and reviewer-token limits remain in force. User stops, authentication/credit errors, refusals, and missing token usage in otherwise completed responses pause instead. Failed review recovery preserves the checkpoint and reuses matching passing checks. Existing failed automatic chats select an alternative when explicitly resumed; server startup does not resume tasks. CheapOS never substitutes local work or a paid route automatically. A reported charge stops work before returned tools execute. Catalog prices and a zero-dollar cap are not provider-side billing guarantees: inspect OmniRoute's own fallbacks and billing settings.

When an automatic worker reaches its response output cap, CheapOS retries once per model per user request with instructions for one small next action. It disables optional reasoning or lowers mandatory reasoning only when current model metadata advertises a supported control. The cap stays unchanged; the retry counts against worker turns, checkpoint turns, time, and usage. If that model reaches the cap again, it enters cooldown and recovery selects a different free worker within the same two-handoff limit. A saved output-limit error enters this recovery on explicit Retry. Interrupted analysis is not replayed. Manual/local workers and reviewers still pause at an output cap. Both streamed and JSON responses discard all tool calls on `finish_reason=length`; final reported usage is counted, or the conservative reservation remains when unavailable. Reported charges stop free recovery. Thinking remains visible during normal requests; recovery changes only the affected worker's reasoning setting. Controls follow [OpenRouter's model reasoning metadata](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).

Malformed edit arguments or oversized edits switch automatic workers to small line edits for the rest of that user request. `replace_lines` sends only the new text for an inclusive line range and checks the current file's SHA-256 hash before writing. Each call replaces at most 80 old lines with at most 80 new lines / 3,000 UTF-8 bytes. New files are created in small chunks. Fresh numbered file excerpts, recent results, and check/review feedback replace malformed call history; incomplete excerpts stay marked. This recovery and supported reasoning reductions persist through successful edits, worker handoffs, and Resume. A new user message resets them. No extra turn allowance, automatic command approval, or review bypass is granted.

CheapOS records file versions from the numbered evidence supplied to the worker; models do not copy hashes into edit arguments. All edits in one model response use the versions available before those edits. A changed or previously unseen file rejects the edit and returns fresh numbered lines for the next response. Successful edits also return updated lines. This prevents one edit in a batch from silently authorizing another against shifted line numbers.

Invalid saved verification commands, including legacy shell redirects or pipes, return correction feedback to the worker before any test execution, reviewer selection, or iteration is consumed. This applies to explicit checkpoints, automatic submission after a final response, and resumed checkpoints. The worker must submit a valid command through `run_checks`; the usual command permission still applies.

The gateway catalog refreshes every five minutes while the interface polls it and on selection when stale. When OmniRoute advertises an OpenRouter connection, CheapOS also reads OpenRouter's public catalog without credentials or project data. This updates named free variants, prices, and tool support, removes retired free routes, and discovers new ones even if OmniRoute's bundled catalog is older. An unavailable upstream catalog pauses discovery rather than trusting stale free entries. A successful tool check ranks ahead of untested candidates with otherwise equal compatibility history.

Model failures enter a persistent 15-minute cooldown, increasing to at most an hour on repeated failures. OmniRoute errors with a valid `Retry-After` instead follow that retry time: explicit `model_cooldown` errors affect that model; otherwise CheapOS conservatively treats the connection as cooling down. Other models on that provider are skipped without compatibility failures, while unrelated providers remain eligible during selection. Resuming early does not repeat those probes. Cooldown expiry allows a new check; it does not prove recovery. Records live in `.cheapos/model-health.json` and contain compatibility counts, timing, and failure diagnostics, not credentials or model output. **Models → Free model pool** distinguishes model and provider cooldowns. Models absent from the latest catalog are never selected from this history.

OmniRoute owns provider/account health, routing, and configured fallbacks. CheapOS observes the final response and owns task recovery. Although OmniRoute supports virtual free routes, CheapOS selects named routes here to keep distinct worker/reviewer model IDs and visible handoffs. Inspect gateway configuration if aliases or upstream fallback can change their underlying identities.

The interface records each handoff with both model names. File actions record the model that performed them. The reviewer receives the original requests, patch, verification output, and read-only tools. Command execution and reviewer takeover retain their approval steps.

## Command permissions and resuming

For a verification command, choose **Run once**, **Allow for this session**, or **Decline** in Chat or Activity. Session permission applies only to that exact command and argument list in the current chat's task copy. It includes repeated verification at checkpoints and survives Pause, Resume, and follow-up messages. Different commands, arguments, workspaces, and chats still require approval. Grants are held in memory and expire when the CheapOS server restarts; saved approval events do not restore permission.

Open **Details → Session permissions** to inspect or clear remembered commands. Clearing affects future executions; a command already running continues. Existing exact-command permissions on legacy or scripted demo tasks remain separate.

**Resume** continues a normal pause with the saved models and limits. A budget stop opens the limits dialog, and reviewer takeover still requires explicit approval. Use the spending button to edit limits separately.

## Keep a slow model from wandering

New runs default to:

- **12 worker turns between checkpoints:** a reminder two turns before the limit asks the worker to verify and wrap up. At the limit it pauses, preserving edits. This interval is independent of the overall worker-turn allowance: raising that allowance to 100 still leaves 12 turns per checkpoint interval. The pause names both counts; Resume starts a new interval within the remaining overall allowance.
- **15 minutes per run:** approval waits do not count. Increase this under **Spending & limits → Advanced limits** for longer work, up to 12 hours.
- **Repeated reads without new evidence:** rereading covered lines at the same file version counts as repetition even when the requested range changes. New lines and changed file versions remain readable. A compact recovery snapshot counts as supplied evidence. After a warning and another repeat, conversations with unfinished edits switch to a bounded next action: edit, verify, submit a checkpoint, or explain a blocker. Reading tools are unavailable for that step. Research without a pending patch gets one answer step. Existing turn, time, and spending limits still apply, and an interrupted response requires Retry.
- **40 worker/coordinator calls per user request:** a follow-up gets a fresh allowance. Resume and server restarts preserve the calls used on that unfinished request. The chat's total call count remains visible in Details. Older chats recover request counts from saved events, conservatively including attempts without a model event.
- Dollar, reviewer-token, and iteration limits remain cumulative across the chat. Single-task non-chat runs retain their task-wide worker-turn cap.

The run timer is checked before inference, as stream chunks arrive, and before executing returned tools. A stalled network call can take its request timeout to return. Resuming starts a fresh progress window and preserves cumulative usage. A progress pause is not completion or approval.

Related edits can be batched in one model response. Context compaction retains the latest distinct reads, shortens large previews, and uses the saved diff instead of replaying full edit arguments.

Small-edit recovery retains completed assistant/tool exchanges between turns. When rebuilding context after interruption or compaction, files that fit the excerpt allowance are included in full; a narrow read cannot shrink that snapshot. Old hashes are omitted from historical summaries so the current file version is unambiguous. Verification commands containing unquoted shell pipes, redirection, or chaining are rejected before permission prompts or execution. CheapOS captures command output itself.

## Activity shows evidence

**Activity** is a visible tab beside Chat. It shows current status, a pending command approval or resume action, all saved file changes, and check/review results for the latest user request. Checks or reviews for an older patch are labeled accordingly. Passing checks alone never imply reviewer approval.

A timeline lists recent actions newest first, including named files, failures, routing checks, and model handoffs. Open a file action to inspect the result or jump to its current diff. The complete technical event log stays collapsed underneath. Chat remains the place for conversation and live model output.

## Validation

Automated fixtures cover local-chat tool isolation, delegation through edit/check/review, different free model selection, failed and charged probes, local-only placement, persisted choices, follow-ups, and progress limits. They make no live inference requests. These tests establish controller behavior; live provider availability, coding quality, and cost savings require separate experiments.

A [live 31-second delegation smoke test](experiments/2026-09-13-delegation.md) also completed the full loop with Gemma, a free Cohere worker, and a different free Dots reviewer.

## Archived and trashed tasks

Archive removes a task from active history. Restore it before continuing work.
Trash retains the conversation and all saved task files on disk; it changes no
source repository files or commits. Restoring a trashed task returns it to its
previous active/archived state and never starts work or restores command grants.
Active runs and unresolved commit transactions must finish or stop first.
There is no automatic cleanup or permanent purge in this version.

## Session test authorization

Recognized unittest commands offer **Allow project tests for this session**.
The displayed scope binds a Python executable and supported selectors/discovery
flags to specific test roots and a known project. It can cover other CheapOS
copies of that project. Tests execute repository code, including later edits.
Changing runner configuration, the executable, or the registered project/copy
requires another decision. Unknown command forms retain exact-command approval.

**Tests allowed this session** beside the composer lists project grants and
exact commands separately. Revoke a project grant or clear this chat's exact
commands there. Grants expire on server restart; revocation does not terminate
an already running command. Command permission never implies passing checks or
approval to commit. Run once and Decline remain available.

### Verification time and evidence

New tasks allow 360 seconds per verification command (the measured CheapOS full
suite took 267 seconds). Advanced limits exposes `check_seconds`, from 1 to 1800.
Old tasks without this field keep 90 seconds until their limits are explicitly
updated. The effective command allowance is always capped by the current run's
remaining working time; it does not change spending, token, or turn caps.
Process timeout, task deadline, output limit, user pause, and a failing test
process have separate outcomes. Infrastructure limits pause with a next action.

Checkpoints and commit readiness share a versioned identity covering the task
copy, baseline, generation, patch, exact argv, executable, virtual environment
configuration, known dependency configuration and installed-package file stats.
A renamed/pinned task does not change that identity. Explicit run_checks always
executes; checkpoint reuse requires matching passing evidence. A focused command
verifies only that command, not the full suite. For documentation work, choose an
appropriate documented check (for example a formatting/link check); a successful
command is not presented as invented code-test coverage.

Old check records remain visible, but lack the new identity and need fresh
verification/review before commit. Rollback still uses workspace generation to
locate historical patches, independently of their current verification validity.
No arbitrary environment values are persisted. Unknown executable/environment
identity is conservatively untrusted; this is evidence tracking, not an OS sandbox.
