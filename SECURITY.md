# Security and trust boundaries

cheapoS is a local experimental coding agent for trusted personal repositories. It is not designed to safely execute untrusted code.

The HTTP server listens on `127.0.0.1`, validates Host/Origin and cross-site request metadata, requires a per-process request token for mutations, disallows framing, and serves only its explicit UI asset allowlist. These controls protect against ordinary cross-origin websites; they do not protect against other processes running as your user. Do not reverse-proxy or expose the app to a network.

The worker's file tools operate inside a task copy and reject traversal, symlinks, Git internals, and common secret filenames. File exclusion is not a secret scanner. Source content, diffs, and command output may reach configured remote model providers. Review provider policies and your source before using them.

By default, the verification command is user supplied and runs on the host. It can access files and network resources available to your user. Clearing its environment and using a separate HOME reduce accidental credential exposure, but are not OS isolation. Repository code—including code edited by the model—can affect host resources when you approve its execution. An optional [Linux Bubblewrap backend](docs/development/command-isolation.md) provides offline command isolation with restricted mounts and a clean environment. It is explicitly selected per task, fails closed when unavailable, and does not claim zero risk. The host mode remains available; previews are disabled for isolated tasks.

The optional **Allow task commands** permission lets the worker choose setup and diagnostic commands as well as checks inside the selected task copy. It is shown at plan approval, applies to that task only, persists across restarts, and can be revoked while paused through Session permissions. Dependency installation can execute package scripts with the same selected backend as other commands (host access in host mode; offline mounts in Bubblewrap mode). Directory checks constrain the initial working directory, not everything the process can access. Required verification and independent review still apply; deployment, publishing, credential access and changes to other checkouts are not authorized.

Session-only API keys stay in process memory. When **Remember this key on this computer** is selected, gateway client keys are stored in macOS Keychain or Linux Secret Service (`secret-tool`). The option is selected by default on supported computers; turn it off for a session-only key. There is no plaintext storage fallback. The API adapter rejects redirects to avoid forwarding credentials to an unexpected endpoint. Configuration and task records use private local files. Provider secrets are not passed in the verification process environment.

OmniRoute is an optional local companion. cheapoS can start the installed CLI on loopback and only stops processes it owns in the current session. Provider credentials remain in OmniRoute; its client API key is held in cheapoS memory, restored from the chosen OS credential store, or supplied by the launch environment. The gateway may implement its own retries and routing, so its configuration is part of the trust boundary. Catalog metadata advertises capabilities; it is not evidence of successful inference or a billing guarantee.

Interrupted work and uncertain provider responses retain their saved records. Eligible failures can continue on another authorized route; operator-paused work stays paused. Cost reservations are estimates and are not a substitute for provider-side spending limits.

Do not publish real credentials or private repository content in bug reports. For vulnerabilities, report them privately via GitHub Security Advisories or email security@cheapos.lol. Otherwise, open a minimal issue asking for a private reporting channel without exploit details or sensitive data.

Automatic startup can send a small greeting to an installed local Ollama model or an eligible configured free route. New cloud fallback requires an explicit opt-in; a saved free provider choice is reused. Greeting requests contain no repository contents and expose no tools. Catalog prices and free-route IDs are eligibility signals, not provider-side billing guarantees. Unknown prices and automatic combos are excluded. A reported charge stops fallback and disables automatic startup. Existing chats keep their original model pair.

## Optional Club sharing

Sharing is off by default. Linking an X account through the Club website and enabling
sync sends signed usage events: a pseudonymous installation/event identity, day,
compute category, input/output token counts, and agent role. It also sends aggregate
completed/merged/review-approved task counts and acceptance rate. Model names are
included only when the separate model-sharing option is enabled. Prompts, source
files, task titles, file paths, command output and API keys are not part of this
payload. The receiving service still observes ordinary connection metadata, such
as your IP address, and links the public profile to the selected X identity.

Pause sharing or disconnect in **Settings → Usage & sharing**. This stops future
uploads; it does not retract data already received. Club signing keys use the OS
credential store and need the optional `requirements-club.txt` dependency. Local
coding works without Club or that dependency.
