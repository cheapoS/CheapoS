# CheapOS

**Cheap models work. Smart models check.**

CheapOS is an open-source, local coding workspace experimenting with a simple trade: give an inexpensive model time to implement a change, then ask a stronger model to review the evidence at checkpoints.

**CheapOS decides why and when to spend intelligence. OmniRoute decides where to get it.** CheapOS owns task execution, verification, review checkpoints, and budget accounting. Its optional OmniRoute companion owns provider access and routing. Explicit model choices keep those responsibilities separate.

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

Click **Try the local demo** first. It creates a tiny Python repository, reproduces a failing test, edits the implementation, requests a revision, adds a regression test, and exports a real Git patch. Model decisions are scripted and clearly labeled. No provider requests or charges occur.

## Connect models

Open **Connections**. OmniRoute is the first-class local gateway, with separate model choices for the worker and reviewer. Direct OpenRouter, Ollama, and other OpenAI-compatible endpoints remain available per role.

### OmniRoute companion

Install and configure [OmniRoute](https://github.com/diegosouzapw/OmniRoute) separately using its official instructions. CheapOS uses your installed `omniroute` command and existing provider configuration; it does not bundle, install, or update it. The integration was checked against OmniRoute 3.8.49.

On launch, CheapOS checks `http://127.0.0.1:20128/v1/models`. It reuses an identified OmniRoute instance or starts the installed CLI on loopback when **Start installed OmniRoute when CheapOS launches** is enabled (the default). Startup runs in the background, so your local task history and patches stay accessible if the gateway fails. An occupied port or rejected client key does not trigger another server.

1. In **Connections**, use **Open OmniRoute** to manage providers and their credentials.
2. Use **Connect / start** or **Refresh models** to load the catalog. If required, enter a gateway client API key under **Startup & connection settings**; this is separate from the dashboard password.
3. Choose **OmniRoute (shared local gateway)** for each role, then pick an explicit model. The picker shows advertised tool support and context size. Catalog access does not prove that a model can complete a task.
4. For free tests, leave **Show free models only** checked and choose explicit OpenRouter `:free` variants for both roles. Unknown prices stay blank and must be supplied. New tasks default to a zero dollar cap when both configured model prices are zero.
5. Save the connections, create a small task, and start it explicitly.

The free filter only filters the catalog; it is not a gateway billing control. CheapOS does not select fallback models. Check OmniRoute's own retries, combos, and fallback policies: `auto/cheap` is not a guarantee of free inference. A zero dollar cap uses configured prices and does not guarantee provider-side billing limits.

OmniRoute also supports Ollama, allowing a local worker and a remote reviewer through the same gateway. Configure the local provider in OmniRoute, then refresh the catalog in CheapOS. If the catalog omits prices, disable the free-model filter to find it and enter zero prices only for a model actually running locally. A direct Ollama connection is also available below. Local inference still depends on your hardware and the model's tool support; that pairing has not been validated by the initial live experiment.

**Keep OmniRoute running when CheapOS closes** is enabled by default, allowing other clients to keep using it. Disable it to stop a process started by the current CheapOS session on exit. CheapOS never stops an instance it merely reused. Startup preferences are saved in `.cheapos/gateway.json`; gateway client keys remain in memory, or can be supplied with `CHEAPOS_GATEWAY_API_KEY` in the launch environment.

### Direct connections

- **OpenRouter:** `https://openrouter.ai/api/v1`. Enter exact model IDs and current input/output prices from the provider.
- **Ollama:** `http://127.0.0.1:11434/v1`, with an installed model supporting tool calling. Local model prices can be zero.
- **Other endpoints:** HTTPS OpenAI-compatible Chat Completions APIs supporting tools, `max_tokens`, and response token usage. Plain HTTP is allowed only on loopback.

Direct API keys entered in the interface remain in server memory until it stops. They are not saved in browser storage, configuration, or task history. You can alternatively supply `CHEAPOS_WORKER_API_KEY` and `CHEAPOS_REVIEWER_API_KEY` through the launch environment. Managed OmniRoute connections use the shared gateway key rather than direct provider keys. CheapOS does not load `.env` files automatically.

Saving, startup, and catalog refresh make no inference requests. Automated tests cover the worker/reviewer workflow through local HTTP fixtures. In the initial live free-model experiment, the worker produced a patch that passed six tests, but the reviewer timed out; the full live loop and cost savings remain unproven. A chat subscription does not automatically provide API credits.

References: [OmniRoute](https://github.com/diegosouzapw/OmniRoute), [OpenRouter tool calling](https://openrouter.ai/docs/guides/features/tool-calling), [OpenRouter limits](https://openrouter.ai/docs/api-reference/limits), [Ollama compatibility](https://docs.ollama.com/api/openai-compatibility).

## Run a task

1. Click **New task**, enter the root path of a local Git repository, and describe a focused change.
2. Set a verification command, such as `python3 -m unittest discover -v`, and your limits.
3. CheapOS creates a separate copy of eligible tracked and untracked files, including your current edits. Inspect the task and click **Start task**.
4. Approve verification commands when prompted. The worker reads, searches, edits, and iterates. The controller reruns your command before sending a checkpoint to the reviewer.
5. The reviewer can **approve**, **request changes**, or **request takeover**. A takeover pauses for your approval and uses the same remaining budget; its final patch still needs your review.
6. Inspect **Activity**, **Changes**, and **Checks**, then **Export patch**.

The source checkout is not modified by file tools. From the original repository, inspect and apply the downloaded patch:

```sh
git apply --check /path/to/cheapos-TASK_ID.patch
git apply /path/to/cheapos-TASK_ID.patch
```

Snapshots omit common secret filenames, symlinks, dependency directories, and ignored files. This is not comprehensive secret detection. Inspect your repository before sending its contents to a remote provider.

Dependencies are not installed automatically. This alpha works best with small, dependency-light projects. For other projects, create the task, find its copy under **Workspace details**, prepare dependencies there yourself, then start it. Commands are split into arguments without a shell; pipes, shell expansion, and redirection are not interpreted.

**Verification runs repository code on your host computer. A separate copy is not an operating-system sandbox.** Commands require approval by default. The optional per-task permission allows the exact configured command throughout that task, including after the worker changes code it executes. Use repositories you trust. Checks have a 90-second timeout and output limits; child processes are stopped as a group on macOS/Linux. Model API keys are removed from their environment.

## Limits and recovery

- Estimated dollar cap, reviewer token cap, worker model-turn cap, iteration cap, and per-request output cap.
- Before dispatch, conservatively reserve prompt/output usage; reconcile with provider-reported tokens and cost. When cost is absent, calculate it from your configured prices.
- Dollar caps are **estimates**, not guaranteed billing limits. Provider tokenization, pricing, and reported costs can differ. Configure a provider-side spending cap for a billing guarantee.
- CheapOS does not automatically retry failed or ambiguous requests. An intermediary gateway may have its own retry policy. Uncertain reservations remain counted. Missing token usage pauses the task before tools execute.
- Pause stops further tool work; an in-flight model request can take up to 3 minutes to return and may still be billed. Slow free or reasoning models may also require a longer queue wait in an intermediary gateway.
- Tasks, patches, checks, checkpoints, and accounting are saved under `.cheapos/`. Interrupted tasks require an explicit resume and retain their usage. The server never automatically resumes paid work.
- Compaction and resume preserve a bounded history of completed file observations and worker notes alongside the current patch and review feedback, without replaying old tool calls.
- One task runs at a time. A process lock prevents two app servers from using the same data directory.

There is no automatic commit, push, dependency installation, merge, arbitrary shell tool, or production sandbox. Keep tasks small: snapshots are limited to 5,000 files / 100 MB, and review checkpoints to a 30,000-character patch. Task history is currently retained until you remove it locally with the app stopped.

## Development

```sh
python3 -B -m unittest discover -s tests -v
node --check dist/app.js
```

Node is only needed for the optional JavaScript syntax check. Tests use temporary local repositories and HTTP servers; they require no API keys and make no external inference calls.

| Path | Responsibility |
| --- | --- |
| `run.py` | Local launcher and single-process storage lock |
| `cheapos/server.py` | Loopback HTTP API, origin/token checks, static assets |
| `cheapos/engine.py` | Worker/checkpoint/reviewer state machine |
| `cheapos/workspace.py` | Repository copies, constrained file tools, verification |
| `cheapos/providers.py` | Chat Completions adapter and usage reservations |
| `cheapos/gateways.py` | Gateway interface, model discovery, and adapter selection |
| `cheapos/omniroute.py` | Optional local gateway startup, reuse, and process ownership |
| `cheapos/storage.py` | Atomic local task persistence |
| `dist/` | Dependency-free graphical workspace |
| `tests/` | Execution, accounting, isolation, recovery, and API tests |

Next experiments: compare successful task cost against a single-model baseline, validate provider/model pairs, add stronger process isolation, and package the desktop app. Contributions should improve measured correctness and cost—not merely lower the displayed token count.

MIT licensed. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
