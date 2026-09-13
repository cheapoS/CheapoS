# CheapOS

**Cheap models work. Smart models check.**

CheapOS is an open-source, local coding workspace experimenting with a simple trade: give an inexpensive model time to implement a change, then ask a stronger model to review the evidence at checkpoints.

**CheapOS decides why and when to spend intelligence. OmniRoute decides where to get it.** CheapOS owns task execution, verification, review checkpoints, and budget accounting. Its optional OmniRoute companion owns provider access and routing. Each chat keeps its selected model pair; startup can find a free worker automatically.

This is an early, working alpha for small personal projects. It has real repository tools and an execution engine, a desktop-style browser interface, and no account or hosted project requirement. It is not a packaged native desktop application yet. Cost savings are a hypothesis to measure, not a benchmark claim.

## Run locally

Requires **Python 3.9+** and **Git**. No Python or JavaScript packages need installing. Development and verification currently target macOS and Linux.

```sh
git clone git@github.com:carlosa8c/CheapOS.git
cd CheapOS
python3 run.py
```

On macOS, you can also double-click **Start CheapOS.command**. The app opens at **http://127.0.0.1:5173/**. It binds only to the loopback interface. There is no sign-in, telemetry, remote asset loading, or cloud deployment dependency.

```sh
python3 run.py --no-open
python3 run.py --port 5174
python3 run.py --data-dir /path/to/local-task-storage
```

On launch, CheapOS looks for a free worker and asks it to say hello. Installed local Ollama models with advertised tool support work without a key or a setup form. A saved eligible model takes priority; otherwise, already-loaded local models are preferred. If no local model works, **Use free cloud models** opts into configured free routes through OmniRoute. CheapOS never enrolls providers, downloads models, or falls back to a paid model.

The welcome message is real inference with no project context or tools. One startup check tries at most three distinct candidates, with a 512-token output cap per request (128 for direct Ollama, with thinking disabled for this greeting only), a 30-second network timeout, and a 60-second stream limit checked between chunks. Reloading the page does not repeat it. **Startup preferences** controls automatic connection and free-cloud fallback; **Stop connecting** cancels it. The greeting verifies chat and token reporting, not completion of the coding loop.

An existing reviewer is preserved. On a fresh setup, the same free model fills both roles, with a separate reviewer request at checkpoints; change either role in **Models** later. A saved paid model or automatic combo is not used for a startup greeting. Startup preferences live in `.cheapos/startup.json`, and the latest check and usage in `.cheapos/startup-last.json`.

You can also click **Try the local demo**. It creates a tiny Python repository, reproduces a failing test, edits the implementation, requests a revision, adds a regression test, and exports a real Git patch. Model decisions are scripted and clearly labeled. No provider requests or charges occur.

## Choose where work runs

Use the execution button beside the chat spending limit to choose **Delegate heavy work**, **All local**, **All remote**, or **Manual model pair**. Local chat can delegate project work to free OmniRoute models and go idle. Automatic remote selection checks tool support and chooses a different reviewer. Existing chats keep their saved setup.

The **Activity** tab shows current status, saved file changes, checks, review decisions, and named model handoffs. Runs pause at progress limits instead of indefinitely rereading files. See [execution choices, free routing, and progress limits](docs/EXECUTION.md).

## Connect models

Open **Models**. OmniRoute is the first-class local gateway, with separate model choices for the worker and reviewer. Direct OpenRouter, Ollama, and other OpenAI-compatible endpoints remain available per role.

### OmniRoute companion

Install and configure [OmniRoute](https://github.com/diegosouzapw/OmniRoute) separately using its official instructions. CheapOS uses your installed `omniroute` command and existing provider configuration; it does not bundle, install, or update it. The integration was checked against OmniRoute 3.8.49.

On launch, CheapOS checks `http://127.0.0.1:20128/v1/models`. It reuses an identified OmniRoute instance or starts the installed CLI on loopback when **Start installed OmniRoute when CheapOS launches** is enabled (the default). Startup runs in the background, so your local task history and patches stay accessible if the gateway fails. An occupied port or rejected client key does not trigger another server.

1. In **Models**, use **Open OmniRoute** to manage providers and their credentials.
2. Use **Connect / start** or **Refresh models** to load the catalog. If required, enter a gateway client API key under **Startup & connection settings**; this is separate from the dashboard password.
3. Choose **OmniRoute (shared local gateway)** for each role, then pick an explicit model. The picker shows advertised tool support and context size. Catalog access does not prove that a model can complete a task.
4. For free tests, leave **Show free models only** checked and choose explicit OpenRouter `:free` variants for both roles. Unknown prices stay blank and must be supplied. New chats default to a zero-dollar cap. Change the cap explicitly before using paid models.
5. Save the connections, open a project, and send a message.

The free filter only filters the catalog; it is not a gateway billing control. Running chats never switch models automatically. Startup connection checks can try other eligible free candidates before a chat begins. Check OmniRoute's own retries, combos, and fallback policies: `auto/cheap` is not a guarantee of free inference. A zero dollar cap uses configured prices and does not guarantee provider-side billing limits.

OmniRoute also supports Ollama, allowing a local worker and a remote reviewer through the same gateway. Configure the local provider in OmniRoute, then refresh the catalog in CheapOS. If the catalog omits prices, disable the free-model filter to find it and enter zero prices only for a model actually running locally. A direct Ollama connection is also available below. Local inference depends on your hardware and the model’s tool support. A local `gemma4:31b` connection has been checked with real file reads, a project question, and a follow-up in the same chat. That check verified conversational use. A later [31-second live delegation experiment](docs/experiments/2026-09-13-delegation.md) used Gemma for a short handoff, a free remote worker for edits, and a different free reviewer; verification passed and the reviewer approved the small patch.

**Keep OmniRoute running when CheapOS closes** is enabled by default, allowing other clients to keep using it. Disable it to stop a process started by the current CheapOS session on exit. CheapOS never stops an instance it merely reused. Startup preferences are saved in `.cheapos/gateway.json`; gateway client keys remain in memory, or can be supplied with `CHEAPOS_GATEWAY_API_KEY` in the launch environment.

### Direct connections

- **OpenRouter:** `https://openrouter.ai/api/v1`. Enter exact model IDs and current input/output prices from the provider.
- **Ollama:** `http://127.0.0.1:11434/v1`, with an installed model supporting tool calling. Local model prices can be zero.
- **Other endpoints:** HTTPS OpenAI-compatible Chat Completions APIs supporting tools, `max_tokens`, and response token usage. Plain HTTP is allowed only on loopback.

Direct API keys entered in the interface remain in server memory until it stops. They are not saved in browser storage, configuration, or task history. You can alternatively supply `CHEAPOS_WORKER_API_KEY` and `CHEAPOS_REVIEWER_API_KEY` through the launch environment. Managed OmniRoute connections use the shared gateway key rather than direct provider keys. CheapOS does not load `.env` files automatically.

Saving settings and refreshing the catalog make no inference requests. The separate startup connection check makes the bounded greeting request described above. Automated tests cover the worker/reviewer workflow through local HTTP fixtures. The initial live free-model experiment reached passing checks but timed out at review. A later [small live delegation test](docs/experiments/2026-09-13-delegation.md) completed edits, verification, and a separate reviewer approval. Cost savings and reliability on larger tasks remain unproven. A chat subscription does not automatically provide API credits.

References: [OmniRoute](https://github.com/diegosouzapw/OmniRoute), [OpenRouter tool calling](https://openrouter.ai/docs/guides/features/tool-calling), [OpenRouter limits](https://openrouter.ai/docs/api-reference/limits), [Ollama compatibility](https://docs.ollama.com/api/openai-compatibility).

## Open a project and chat

1. Click **Open project** and enter the root folder of a local Git repository. It is remembered on this computer; opening it makes no model request.
2. Type a question or describe a change, then send. CheapOS creates a separate task copy and uses your saved model choices and limits.
3. Questions can finish with an answer. For changes, the worker inspects the project, proposes a verification command, and asks for approval in the conversation. The controller reruns checks before requesting a reviewer decision.
4. Keep talking in the same chat. Follow-ups retain the task copy, original model pair, accumulated usage, and prior requests—even after a completed review. **New chat** starts a fresh copy of the source project.
5. Open **Changes** to inspect the diff. After verification and review, choose **Apply & commit**, review the destination branch and editable commit message, then **Approve & commit**. CheapOS applies the patch to your project and makes a local Git commit. **Checks** shows verification output. **Activity** summarizes current work and results; model accounting lives under **Details**.

Your approval is required for each commit; a model's approval cannot authorize it. The preview expires after ten minutes and is rechecked before applying. Your source checkout must be clean, on a branch, and have a configured Git author identity. The exact patch must apply cleanly; unrelated committed changes are preserved. Checks describe the task copy, while the preview identifies the current destination commit. Conflicts or unrelated uncommitted work stop the operation without discarding edits. Git hooks and signing are disabled for this action; repositories with content filters or sparse index flags use the exported patch workflow. A takeover can be committed after passing checks and your explicit review, with its lack of independent approval shown in the preview.

After committing, the chat advances its task baseline so follow-up changes create a new patch. The commit hash and original patch stay in history. An interrupted commit attempt is saved for an explicit retry, and a repeated request cannot create a duplicate commit. Pushing remains separate. **Export patch** is available for manual Git workflows.

The spending control below the message box edits the current chat's limits, or defaults for new chats. Saving limits does not run a model. Model settings apply to new chats; existing chats retain their original model pair. An error never silently changes models or retries a request.

Direct local Ollama connections on port `11434` and OmniRoute connections stream output into the conversation. Models that expose reasoning show an expandable **Thinking** panel while the answer appears separately as it arrives. A progress card shows elapsed time, the last completed action, and saved file changes. Thinking is model output, not evidence that a file was edited or a check passed. Completed and interrupted thinking previews are saved locally, capped at 16,000 characters per response; they are excluded from reviewer checkpoints. Other direct connections currently show progress while waiting for a complete response. Endpoints that return ordinary JSON instead of a stream still work, with output shown on completion.

The reviewer can approve, request revisions, or request takeover. Takeover requires your explicit approval and uses the same remaining budget. Its final patch still needs your review. Plain answers and clarification questions do not count as reviewer approval; saved edits remain available in **Changes**.

### Read a public link

Paste an HTTPS link into Chat and ask about it. The worker and reviewer can use `read_url` to read public text pages; GitHub repository links open the repository's README through [GitHub's contents API](https://docs.github.com/en/rest/repos/contents#get-a-repository-readme). Chat shows the page being opened, the source, and the lines read. Longer documents can be read in sections. **Search project** searches local files only.

The reader can follow links returned by a page. It makes GET requests without cookies, credentials, or project contents, and blocks private/local addresses and redirects to them. Each run can fetch up to eight documents, with a 1 MB response limit and bounded text excerpts; repeated sections use an in-memory cache. It does not provide search-engine results, sign-in, JavaScript interaction, or PDF reading. If a page cannot be read, the worker should explain the error or ask for the relevant text. Retrieved text is untrusted source material, not permission to run commands.

The source checkout is not modified by file tools. From the original repository, inspect and apply the downloaded patch:

```sh
git apply --check /path/to/cheapos-TASK_ID.patch
git apply /path/to/cheapos-TASK_ID.patch
```

Snapshots omit common secret filenames, symlinks, dependency directories, and ignored files. This is not comprehensive secret detection. Inspect your repository before sending its contents to a remote provider.

Dependencies are not installed automatically. This alpha works best with small, dependency-light projects. For other projects, pause the chat, find its copy under **Details → Workspace details**, prepare dependencies there yourself, then resume. Commands are split into arguments without a shell; pipes, shell expansion, and redirection are not interpreted.

**Verification runs repository code on your host computer. A separate copy is not an operating-system sandbox.** Commands require approval by default. Choose **Run once** or **Allow for this session** to remember an exact command for the current chat's task copy, including checkpoint reruns. Different commands still ask. Session grants expire when CheapOS restarts and can be cleared under **Details → Session permissions**. Legacy tasks may separately have a saved permission for their exact configured command. Use repositories you trust. Checks have a 90-second timeout and output limits; child processes are stopped as a group on macOS/Linux. Model API keys are removed from their environment.

## Limits and recovery

- Estimated dollar cap, reviewer token cap, worker model-turn cap, iteration cap, and per-request output cap. In chats, each user message gets its own worker-turn allowance; Resume preserves turns already used on that message. Spending, token usage, and review iterations remain cumulative.
- Before dispatch, conservatively reserve prompt/output usage; reconcile with provider-reported tokens and cost. When cost is absent, calculate it from your configured prices.
- Dollar caps are **estimates**, not guaranteed billing limits. Provider tokenization, pricing, and reported costs can differ. Configure a provider-side spending cap for a billing guarantee.
- CheapOS does not automatically retry failed or ambiguous task requests. The separate startup greeting can try up to three distinct free candidates. An intermediary gateway may have its own retry policy. Uncertain reservations remain counted. Missing token usage pauses the task before tools execute.
- Stop prevents further tool work. Ollama and OmniRoute streams check for cancellation as output arrives; a stalled connection can take 3 minutes to release. Streaming also checks a 10-minute generation limit between chunks. Other model requests retain a 3-minute network timeout and may still be billed after stopping. Partial or interrupted tool calls never execute. Slow free or reasoning models may also require a longer queue wait in an intermediary gateway.
- Tasks, patches, checks, checkpoints, and accounting are saved under `.cheapos/`. Interrupted tasks require an explicit resume and retain their usage. The server never automatically resumes paid work.
- Compaction and resume preserve a bounded history of completed file observations and worker notes alongside the current patch and review feedback, without replaying old tool calls.
- Research keeps a compact record of the sources and sections already read. For a chat request with no new edits, CheapOS reserves the final available research turn for an answer with tools disabled; repeated reads can trigger this earlier. This response uses the same worker and remaining budget. It can report missing information, but cannot approve edits. Resuming a paused read-only loop goes directly to this answer step instead of restarting research.
- One task runs at a time. A process lock prevents two app servers from using the same data directory.

There is no unattended commit, push, dependency installation, merge, arbitrary shell tool, or production sandbox. Keep tasks small: snapshots are limited to 5,000 files / 100 MB, and review checkpoints to a 30,000-character patch. Task history is currently retained until you remove it locally with the app stopped.

## Development

```sh
python3 -B -m unittest discover -s tests -v
node --check dist/app.js
node --test tests/test_guidance.js
```

Node is only needed for the optional JavaScript syntax check. Tests use temporary local repositories and HTTP servers; they require no API keys and make no external inference calls.

| Path | Responsibility |
| --- | --- |
| `run.py` | Local launcher and single-process storage lock |
| `cheapos/server.py` | Loopback HTTP API, origin/token checks, static assets |
| `cheapos/engine.py` | Worker/checkpoint/reviewer state machine |
| `cheapos/workspace.py` | Repository copies, constrained file tools, verification |
| `cheapos/providers.py` | Chat Completions adapter and usage reservations |
| `cheapos/streaming.py` | Bounded streaming output and complete tool-call assembly |
| `cheapos/routing.py` | Execution placement, lightweight local delegation, and bounded free-route checks |
| `cheapos/startup.py` | Free-worker discovery, startup greeting, and connection-check accounting |
| `cheapos/gateways.py` | Gateway interface, model discovery, and adapter selection |
| `cheapos/omniroute.py` | Optional local gateway startup, reuse, and process ownership |
| `cheapos/storage.py` | Atomic local task persistence |
| `dist/` | Dependency-free graphical workspace |
| `tests/` | Execution, accounting, isolation, recovery, and API tests |

Next experiments: compare successful task cost against a single-model baseline, validate provider/model pairs, add stronger process isolation, and package the desktop app. Contributions should improve measured correctness and cost—not merely lower the displayed token count.

MIT licensed. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
