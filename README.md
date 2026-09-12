# CheapOS

**Cheap models work. Smart models check.**

CheapOS is an open-source, local coding workspace experimenting with a simple trade: give an inexpensive model time to implement a change, then ask a stronger model to review the evidence at checkpoints.

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

Open **Connections**. The easiest first setup is **OpenRouter for both roles**: one key, an inexpensive tool-capable worker, and a stronger reviewer. Use the exact model IDs and current input/output prices from your provider.

- **OpenRouter:** `https://openrouter.ai/api/v1`
- **Local Ollama:** `http://127.0.0.1:11434/v1` with an installed model that supports tool calling; prices can be zero.
- **Other providers:** an HTTPS OpenAI-compatible Chat Completions endpoint supporting tools, `max_tokens`, and token usage in responses.

Keys entered in the interface remain in server memory until it stops. They are not saved in browser storage, configuration, or task history. You can alternatively provide `CHEAPOS_WORKER_API_KEY` and `CHEAPOS_REVIEWER_API_KEY` through the launch environment. Do not commit keys or paste them into tasks. CheapOS does not load `.env` files automatically.

Saving connections makes no inference request. Provider compatibility is tested against a local HTTP fixture; live provider/model combinations still need validation with your own credentials. A chat subscription does not automatically provide API credits.

References: [OpenRouter tool calling](https://openrouter.ai/docs/guides/features/tool-calling), [OpenRouter limits](https://openrouter.ai/docs/api-reference/limits), [Ollama compatibility](https://docs.ollama.com/api/openai-compatibility).

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
- Failed or ambiguous requests are not automatically retried. Their reservations remain counted. Missing token usage pauses the task before tools execute.
- Pause stops further tool work; an in-flight model request can take up to 90 seconds to return and may still be billed.
- Tasks, patches, checks, checkpoints, and accounting are saved under `.cheapos/`. Interrupted tasks require an explicit resume and retain their usage. The server never automatically resumes paid work.
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
| `cheapos/storage.py` | Atomic local task persistence |
| `dist/` | Dependency-free graphical workspace |
| `tests/` | Execution, accounting, isolation, recovery, and API tests |

Next experiments: compare successful task cost against a single-model baseline, validate provider/model pairs, add stronger process isolation, and package the desktop app. Contributions should improve measured correctness and cost—not merely lower the displayed token count.

MIT licensed. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
