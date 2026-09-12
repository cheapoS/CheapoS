# Security and trust boundaries

CheapOS is a local experimental coding agent for trusted personal repositories. It is not designed to safely execute untrusted code.

The HTTP server listens on `127.0.0.1`, validates Host/Origin and cross-site request metadata, requires a per-process request token for mutations, disallows framing, and serves only its four UI assets. These controls protect against ordinary cross-origin websites; they do not protect against other processes running as your user. Do not reverse-proxy or expose the app to a network.

The worker's file tools operate inside a task copy and reject traversal, symlinks, Git internals, and common secret filenames. File exclusion is not a secret scanner. Source content, diffs, and command output may reach configured remote model providers. Review provider policies and your source before using them.

The verification command is user supplied and runs on the host. It can access files and network resources available to your user. Clearing its environment and using a separate HOME reduce accidental credential exposure, but are not OS isolation. Repository code—including code edited by the model—can affect host resources when you approve its execution. The current release does not use containers or an OS sandbox.

Model API keys supplied in the UI are kept only in process memory. The API adapter rejects redirects to avoid forwarding credentials to an unexpected endpoint. Configuration and task records use private local files. Provider secrets are not passed in the verification process environment.

Tasks pause after restarts or uncertain provider responses. Cost reservations are estimates and are not a substitute for provider-side spending limits.

Do not publish real credentials or private repository content in bug reports. For vulnerabilities, use the repository's private vulnerability reporting option if available. Otherwise, open a minimal issue asking the maintainer for a private reporting channel, without exploit details or sensitive data.
