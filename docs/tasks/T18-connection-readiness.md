# T18 — Structured onboarding readiness and recovery states

**Depends on:** none. **Size:** M. **Result:** first-run UI can explain exactly what is missing without guessing from error strings.

## Read first

`cheapos/startup.py`, `omniroute.py`, `gateways.py`, server startup/config endpoints, `run.py`, and startup/gateway tests.

## Implementation

1. Define a small versioned readiness response covering local prerequisites and supported connection paths. Distinguish: gateway absent, installed but stopped, starting, ready, incompatible/unknown service on port, client key rejected, no eligible provider/model, local-only ready, and offline/unavailable.
2. Include actionable next-step identifiers and safe diagnostics, not provider secrets or raw config files. Reuse existing gateway snapshots and probes; status inspection must not run inference or install anything.
3. Detect the installed CLI/version and whether CheapOS owns the running process. Existing identified instances are reused; foreign processes are not killed or replaced. Never confuse dashboard credentials with an API client key.
4. Preserve current startup preferences and selected working connections. A successful greeting means chat/usage reporting worked, not that coding/checks/review completed. Expose those readiness levels separately.
5. Capability/version-check any optional OmniRoute API before depending on it. Baseline inspected was 3.8.49; newer upstream docs do not guarantee local API compatibility. Keep fixture coverage for supported/unsupported versions without auto-upgrading.
6. Keep current clients working while adding the readiness payload. Do not block access to task history/diffs when setup fails.

## Acceptance

Fixtures cover absent binary, stopped/ready gateway, occupied foreign port, rejected client key, no eligible free candidate, local-only model, offline, and valid greeting. Readiness calls cause no model request, installation, task mutation, or unwanted process stop. Error next steps are distinct and reproducible.

## Validation / limits

Run startup/gateway/HTTP tests and add response-contract coverage. This card is backend/readiness only: no wizard, installer, automatic model download, or provider enrollment. T19 consumes this response.

## Completion record

Status: Todo

- Behavior delivered: —
- Acceptance evidence: —
- Commands and results: —
- Browser scenarios and results: —
- Remaining limitations: —

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
