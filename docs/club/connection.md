# Club connection (private alpha)

Install the optional signer into the Python environment that launches cheapoS:
`python3 -m pip install -r requirements-club.txt`. Agent work does not import or
require it. Private Ed25519 keys go into the existing OS credential-store adapter,
never a JSON file. Unsupported/locked secure storage disables Club connection,
not local work. The old manual HMAC link is deliberately rejected.

Website setup is documented in the Club repository's `web/CONNECTION_SETUP.md`.
Open **Settings → The Cheapskate Club → Connect to Club**, follow the approval
link, and verify **Connect to @handle**. The Club tab checks approval automatically
while open; **Check connection** also refreshes it. Review the displayed fields
and Enable sharing for new usage. Connection and sharing apply to this installation,
across its projects and chats. Charts and local exports remain in **Usage & savings**.
This also opts your Club profile into public rankings. Existing usage is excluded.
Use Sync now after a new task; background sync checks every minute and backs off
on failures (up to 15 minutes). No models are called by syncing.

Only request counts with reconciled usage are exported. Classification requires
explicit access evidence, not model-name guesses. Unknown and subscription-included
usage is retained separately from the public-free/local boards. Reservations and
old summary exports never count. Later corrections replace the original event
counts; they do not create another full contribution.

Disconnect stops local sharing immediately and asks the service to revoke the
pairing. If offline, it remains pending; retry Disconnect before pairing another
account. The same installation signing key is retained, so changing accounts
cannot reset the service cursor. Previously accepted events keep their old owner.
Unsent old-account work is discarded on confirmed disconnect; it is not transferred.
Connecting again snapshots existing request IDs so they cannot become new usage.
Pausing/resuming sharing likewise excludes requests begun while sharing was off.

State is in `club_connection.json` (public metadata and durable signed outbox).
The outbox and its local request fingerprints are written atomically before send.
Only a matching sequence and SHA-256 acknowledgment advances it. A lost reply
retries identical bytes. The server transaction locks the installation, validates
the sequence/hash, enforces one owner, and records idempotent receipts.

The v1 wire envelope contains a JSON payload STRING, its Ed25519 signature and
public key (hex). Signature input is UTF-8 `cheapskate-club-v1\n` + exact payload
bytes; hash input is the exact payload bytes. This explicitly avoids claiming a
home-grown serializer implements all of RFC 8785. The client emits compact sorted
ASCII JSON with integers. The service verifies before parsing, validates fields,
and retains the digest for exact-retry checks. A Python→Node fixture covers this.

This detects changed signed submissions and duplicate delivery, not fabricated
usage from a modified client. It is app-reported accounting, not verified inference.
No tasks, prompts, code, paths, raw logs, model names, or provider keys are sent.

Validation: 47 focused Python/HTTP tests passed in 11.93s; new Club cases alone
are part of a 0.016s unit run. Six usage UI checks passed in 0.074s. No live models
or full Python suite used. Live signed-in browser pairing still requires deployed
service credentials and migration; do not claim this has been exercised yet.

A disposable loopback end-to-end run also passed: actual Python signing → HTTP →
Node signature verification → SQL pairing/consent/sync → leaderboard. A synthetic
15-token request produced 15 tokens, an identical retry remained 15, and disconnect
was acknowledged. Browser OAuth approval was simulated in that isolated fixture.
