# Security and trust boundaries

cheapoS is a local experimental coding agent for trusted personal repositories. It is not designed to safely execute untrusted code.

The HTTP server listens on `127.0.0.1`, validates Host/Origin and cross-site request metadata, requires a per-process request token for mutations, disallows framing, and serves only its explicit UI asset allowlist. These controls protect against ordinary cross-origin websites; they do not protect against other processes running as your user. Do not reverse-proxy or expose the app to a network.

The worker's file tools operate inside a task copy and reject traversal, symlinks, Git internals, and common secret filenames. File exclusion is not a secret scanner. Source content, diffs, and command output may reach configured remote model providers. Review provider policies and your source before using them.

The verification command is user supplied and runs on the host. It can access files and network resources available to your user. Clearing its environment and using a separate HOME reduce accidental credential exposure, but are not OS isolation. Repository code—including code edited by the model—can affect host resources when you approve its execution. The current release does not use containers or an OS sandbox.

The optional **Allow task commands** permission lets the worker choose setup and diagnostic commands as well as checks inside the selected task copy. It is shown at plan approval, applies to that task only, persists across restarts, and can be revoked while paused through Session permissions. Dependency installation can execute package scripts with the same host access as other commands. Directory checks constrain the initial working directory, not everything the process can access. Required verification and independent review still apply; deployment, publishing, credential access and changes to other checkouts are not authorized.

Model API keys supplied in the UI are kept only in process memory. The API adapter rejects redirects to avoid forwarding credentials to an unexpected endpoint. Configuration and task records use private local files. Provider secrets are not passed in the verification process environment.

OmniRoute is an optional local companion. cheapoS can start the installed CLI on loopback and only stops processes it owns in the current session. Provider credentials remain in OmniRoute; its client API key is held in cheapoS memory or supplied by the launch environment. The gateway may implement its own retries and routing, so its configuration is part of the trust boundary. Catalog metadata advertises capabilities; it is not evidence of successful inference or a billing guarantee.

Tasks pause after restarts or uncertain provider responses. Cost reservations are estimates and are not a substitute for provider-side spending limits.

Do not publish real credentials or private repository content in bug reports. For vulnerabilities, use the repository's private vulnerability reporting option if available. Otherwise, open a minimal issue asking the maintainer for a private reporting channel, without exploit details or sensitive data.

Automatic startup can send a small greeting to an installed local Ollama model or an eligible configured free route. New cloud fallback requires an explicit opt-in; a saved free provider choice is reused. Greeting requests contain no repository contents and expose no tools. Catalog prices and free-route IDs are eligibility signals, not provider-side billing guarantees. Unknown prices and automatic combos are excluded. A reported charge stops fallback and disables automatic startup. Existing chats keep their original model pair.
