# Exporter trial observer

`exporter_live.py` uses the existing branch controller. It does not implement the
feature or bypass Start. Commit T42/T43 and the observer driver before planning;
use a fresh external root and the explicitly authorized pinned profile.

```sh
python3 -B docs/trials/exporter_live.py plan --root /tmp/cheapos-exporter-1 --config-dir /tmp/pinned-profile --input document --access-basis operator_authorized_included --live
```

This permits planning inference only. Inspect `proposal.private.json`, the exact
three implementation items, dependencies, commands, models and spending scope.
The driver checks the T42 manifest against its files and freezes both the manifest
bytes and pack digest. Source is a clone of the exact committed app SHA; state
and copied configuration are outside it. Configuration and proposals are private.
Catalog membership is not a quota or inference readiness check: confirm the
selected authorized connections are currently usable before Start.

```sh
python3 -B docs/trials/exporter_live.py start --root /tmp/cheapos-exporter-1 --reviewed-digest FULL_SHA256 --live
```

Start refreshes the ephemeral proposal and requires the same complete contract.
The driver never retries, resumes, approves new commands, merges or pushes. An
exclusive phase marker also prevents repeating an uncertain attempt. Preserve
failed roots. A changed runtime requires a separately identified attempt.

If the operator corrects a plan through the existing proposal-edit API, save that
API response privately and supply `--proposal-file /tmp/corrected-proposal.json`
with its reviewed digest at Start. The original remains preserved and the result
is labeled planning assisted. The driver does not create the correction.

Public result files contain allowlisted accounting and integrity evidence;
private errors and proposals are not publication material. Execution accounting
is separated from the planning baseline, including retained provenance counts.
Readiness is an application result; T45 still verifies actual browser downloads.

Retain `project/` and `state/` together. Completed source commit SHAs/trees are
recorded; the private workspace may use different SHAs. A Git bundle of the
source feature ref and base, or a fetch into a dedicated review ref, preserves the
actual feature commits for later inspection. Do not merge them to main merely to
retain them. Verify any imported tip/tree against the saved receipts.
