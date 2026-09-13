# Contributing to CheapOS

Small, reviewable changes are welcome. For significant behavior changes, open an issue describing the problem and your proposed approach first.

Run `python3 -B -m unittest discover -s tests -v`, `node --check dist/app.js`, and `node --test tests/test_*.js`. Exercise relevant UI flows with `python3 run.py`. Model execution tests should use deterministic providers and temporary repositories, with no external inference calls or personal API credentials.

For conversation changes, check live worker and reviewer output inside the CheapOS reply, command permission, reviewer revisions, and the final approval controls. Details should stay open through updates and tab switches; returning to Chat should show the latest message. Keep course corrections in chronological order and avoid presenting a failed or unfinished check/review as a success.

Preserve these properties:

- No hosted sign-in or required cloud project.
- No secrets in task records, configuration, browser storage, or test fixtures.
- Usage is reserved before a request and retained when billing is uncertain.
- Reviewer approval follows verification and refers to the actual task patch.
- Commands require the user's task-scoped approval; a snapshot is not described as a security sandbox.
- A provider error does not trigger a hidden retry or model upgrade.
- Savings claims require a measured baseline and comparable task outcomes.

Include what changed, why it helps, and relevant verification in your pull request. Do not commit `.cheapos/`, credentials, local task output, or unrelated generated assets. Code contributions are made under the repository's MIT license.
