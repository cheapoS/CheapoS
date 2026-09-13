# T20 — Local-only onboarding and an honest sample loop

**Depends on:** T19, T10. **Size:** M. **Result:** the app works without OmniRoute and clearly distinguishes a greeting, a demo, and a real completed loop.

## Read first

Local candidate discovery/verification, coordinator/tool isolation, execution modes, `create_demo`, existing fixture providers, and the documented live delegation experiment.

## Implementation

1. Finish the local-only path in onboarding. Detect installed eligible Ollama models; show name, advertised tool capability, and measured readiness when available. Do not select a cloud-forwarding alias just because the endpoint is localhost.
2. Preserve the operator's placement choice. For laptop delegation, local chat stays brief and remote work requires explicit free-cloud selection. All local deliberately keeps work/review local. Do not claim a large local model will be fast without evidence.
3. If no local model is installed, provide setup/model-download guidance and a scripted demo option. No silent large model download. Any future automatic download needs a separate explicit choice showing size and destination.
4. Add `Try a sample task` with two unmistakable choices: scripted demonstration, or a real loop using currently selected models. Explain what will run before start. Create a disposable repository independent of the user's selected project.
5. The real sample uses a small fixed request, bounded budget/time, actual file tools/checks, and a separate review request. Authorize only its known verification command for the disposable fixture through the sample action; do not grant test permission to unrelated projects.
6. Show real stage evidence and final outcome. Passing greeting/tool probe is not full-loop success. Failure offers connection/model diagnostics without claiming onboarding is complete. Keep saved sample results inspectable and removable through normal task controls.

## Acceptance

Local-only can greet and work with compatible fixtures while all remote requests are rejected. No-model path remains usable via scripted demo. Real sample success requires edits, passing checks, and review; inject a check failure and reviewer outage to verify accurate outcomes. User repository files/HEAD and task work remain untouched.

## Validation / limits

Use local deterministic provider fixtures for automated tests; an operator may later run the labeled real sample with their own selected models. Do not use credentials from the development machine in tests or equate a same-model local review with a different-model review. No native packaging or automatic model installation in this card.

## Completion record

Status: Todo

- Behavior delivered: —
- Acceptance evidence: —
- Commands and results: —
- Browser scenarios and results: —
- Remaining limitations: —

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
