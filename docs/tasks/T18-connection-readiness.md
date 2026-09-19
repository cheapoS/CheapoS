# T18 — Structured onboarding readiness and recovery states

**Depends on:** none. **Size:** M. **Result:** first-run UI can explain exactly what is missing without guessing from error strings.

## Read first

`cheapos/startup.py`, `omniroute.py`, `gateways.py`, server startup/config endpoints, `run.py`, and startup/gateway tests.

## Implementation

1. Define a small versioned readiness response covering local prerequisites and supported connection paths. Distinguish: gateway absent, installed but stopped, starting, ready, incompatible/unknown service on port, client key rejected, no eligible provider/model, local-only ready, and offline/unavailable.
2. Include actionable next-step identifiers and safe diagnostics, not provider secrets or raw config files. Reuse existing gateway snapshots and probes; status inspection must not run inference or install anything.
3. Detect the installed CLI/version and whether cheapoS owns the running process. Existing identified instances are reused; foreign processes are not killed or replaced. Never confuse dashboard credentials with an API client key.
4. Preserve current startup preferences and selected working connections. A successful greeting means chat/usage reporting worked, not that coding/checks/review completed. Expose those readiness levels separately.
5. Capability/version-check any optional OmniRoute API before depending on it. Baseline inspected was 3.8.49; newer upstream docs do not guarantee local API compatibility. Keep fixture coverage for supported/unsupported versions without auto-upgrading.
6. Keep current clients working while adding the readiness payload. Do not block access to task history/diffs when setup fails.

## Acceptance

Fixtures cover absent binary, stopped/ready gateway, occupied foreign port, rejected client key, no eligible free candidate, local-only model, offline, and valid greeting. Readiness calls cause no model request, installation, task mutation, or unwanted process stop. Error next steps are distinct and reproducible.

## Validation / limits

Run startup/gateway/HTTP tests and add response-contract coverage. This card is backend/readiness only: no wizard, installer, automatic model download, or provider enrollment. T19 consumes this response.

## Completion record

Status: Done

- Behavior delivered: GET `/api/readiness` returns schema version 1, typed recovery actions, safe prerequisite/version/ownership metadata, local availability, and separate catalog/greeting/work readiness levels. Probes are background, bounded and cached; explicit refresh remains metadata-only.
- Acceptance evidence: Deterministic fixtures cover absent Node/CLI, stopped/starting/ready/foreign/auth/offline/empty catalog, local selection, greeting, version compatibility, secret omission, and no startup inference. Existing gateway lifecycle tests cover reuse and foreign-process ownership.
- Commands and results: `PYTHONPATH=tests python3 -B -m unittest test_readiness test_startup test_gateways test_http -q`: 67 passed in 29.155s. Added HTTP readiness test: 1 passed in 0.016s.
- Browser scenarios and results: Backend-only card; UI coverage follows in T19.
- Remaining limitations: Installed CLI version is not proof of the running service version. Optional setup/enrollment APIs remain disabled for all versions; the dashboard is the supported fallback. No installs, upgrades, inference, or foreign-process stops are performed.

Before implementing, read [TASKS.md](../archive/TASKS.md) for the shared contract. Update this record and the matching board row when complete.
