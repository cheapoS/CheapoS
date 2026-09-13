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

Status: Done

- Behavior delivered: Local setup lists eligible installed Ollama names, advertised capabilities and honest greeting/work readiness. All local explicitly saves local work/review placement with cloud startup disabled. Cloud aliases are filtered. Sample chooser separates scripted UI demonstration from a real bounded local/disposable repository loop; exact sample verification permission is task/session scoped. Outcomes require actual edits/checks/review and label same-model local review.
- Acceptance evidence: Automated complete local sample, check failure and reviewer outage; provider fixture rejects nonlocal endpoints. Source files/HEAD preserved. No project-wide test grant created. HTTP sample creation creates no running task. Existing startup tests cover local greeting and isolation.
- Commands and results: 23 sample/startup/readiness tests passed (10.787s); 12 engine/API tests passed (8.941s); final 3 sample tests passed (10.302s). JavaScript syntax and 68 guidance/conversation tests passed.
- Browser scenarios and results: CUA isolated port 51029: eligible local picker saved All local; real sample made edits, ran four tests and a separate same-model reviewer request, ending at human commit approval. No-model path showed manual setup guidance and successfully ran the separately labeled scripted demo. Saved samples remained in history. Shared responsive dialog uses the T19 overflow fix.
- Remaining limitations: Downloads/install remain manual via https://ollama.com/download; tool-capability guidance follows https://docs.ollama.com/capabilities/tool-calling. No performance claim or live personal model test. Same-model review is explicitly identified. Sample command authorization expires on server restart; final commit remains a separate operator decision.

Before implementing, read [TASKS.md](../../TASKS.md) for the shared contract. Update this record and the matching board row when complete.
