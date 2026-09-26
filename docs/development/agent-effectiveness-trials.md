# Comparable local agent-effectiveness trials

Use the existing metrics exporter to compare **saved** trials. This is an offline,
read-only reporting workflow: it does not dispatch models, run checks, change
permissions, resume work, or publish Club statistics. It does not replace task
review or grant approval. Task snapshots can contain private content: keep inputs
and assessment evidence locally; share only an inspected export.

## Capture a comparison before running it

Write down the cases, number of repetitions, variants, completion rubric and
permitted interventions before selecting outcomes. Give every planned run a
stable case, variant and positive repetition number. Include failed, paused,
cancelled and unfinished trials; do not select only successes. Keep one snapshot
per run, replacing that snapshot when it advances rather than counting Resume as
another trial. A follow-up in the same chat is not an independent trial.

Keep five common inputs whose SHA-256 fingerprints form the comparison contract:

- `source_sha256`: the fixed starting source/content snapshot, including fixtures.
- `requirements_sha256`: the task requirements and completion rubric.
- `checks_sha256`: exact required commands, working directories and acceptance pack.
- `environment_sha256`: OS/runtime/dependency/tool versions and execution environment.
- `authority_sha256`: approved placement, allowed models, spending and command policy.

The variant label identifies the intended difference. Record its exact settings
in the experiment protocol alongside these files. For example, comparing two
models requires an authority contract that permits both; changing the permitted
spending or commands between runs does not establish a comparable efficiency
result. Fingerprints are operator declarations, not independently checked proof
that environments or requirements actually matched. Keep the source files for
audit. Missing fingerprints make a pair noncomparable.

For future **separately authorized** Unattended trials, set `measurement: true` on
the planning request or `plan.measurement: true` on an operator-prepared proposal.
Capture authorization normally, including free-only placement when selected.
Measurement mode removes censoring by arbitrary work caps; it does not grant
spending, new models, commands or recurrence. Preserve failures, pauses, usage and
interventions. Do not substitute large caps or reset an allowance. Export reads
the saved `branch_run.plan.measurement`; different or unknown modes prevent model
trial comparison. Interactive snapshots without this evidence remain reportable,
but their pairs are marked noncomparable. No live trial is needed to use or test
the exporter.

## Build a manifest and export

Copy each selected saved `tasks/<task-id>/task.json` into a private local trial
folder. Stop at a defined observation boundary and retain the originals. The
example below assumes `one.json`, `two.json`, the five contract input files, and
two assessment files exist in the current trial folder. Assessment files contain
an explicit completion judgment against the fixed rubric and supporting check,
review and outcome evidence; they are not task approval receipts. A status such
as `approved` alone does not establish experimental completion. If assessment is
not available, omit `assessment` instead of inventing a result.

```python
import hashlib
import json
from pathlib import Path


def sha(name):
    return hashlib.sha256(Path(name).read_bytes()).hexdigest()


contract = {
    'source_sha256': sha('source-manifest.json'),
    'requirements_sha256': sha('requirements.md'),
    'checks_sha256': sha('checks.json'),
    'environment_sha256': sha('environment.json'),
    'authority_sha256': sha('authority.json'),
}
trials = []
for identity, variant in [('one', 'baseline'), ('two', 'candidate')]:
    assessment = json.loads(Path(identity + '-assessment.json').read_text())
    trials.append({
        'id': identity, 'case': 'bounds', 'variant': variant, 'repeat': 1,
        'kind': 'recorded_model_trial', 'source': identity + '.json',
        'contract': contract,
        'assessment': {'completed': assessment['completed'],
                       'evidence_sha256': sha(identity + '-assessment.json')},
    })
Path('trials.json').write_text(json.dumps({'schema_version': 1, 'trials': trials}))
```

Run from the cheapoS checkout with explicit local paths:

```sh
python3 -B scripts/task_metrics.py --trials /tmp/local-trials/trials.json --output /tmp/local-trials/comparison.json --markdown /tmp/local-trials/comparison.md
```

Source paths resolve relative to the manifest; absolute input paths also work.
Outputs must differ from the manifest, every source snapshot and each other.
IDs use 1–80 ASCII letters, digits, dots, underscores or hyphens, beginning with a
letter or digit. IDs are exported: use neutral labels, never secrets or paths.
JSON schema version is 1. Duplicate IDs or case/variant/repetition slots are
rejected. Reusing a task or the same fixture snapshot anywhere in a manifest,
including another repetition, is also rejected. Fingerprints are 64 lowercase hexadecimal characters or null.

Pairs share case and repetition and have different variant labels. The report
shows every trial, completion counts (including unknowns), unpaired trials and
reasons for incompatible pairs. Reusing the same task under different snapshots
cannot manufacture independent comparisons. Numerical deltas are right minus
left, available only for compatible pairs with explicit completion on both sides
and known values. They are observations, not savings, causal effects or evidence
that a model is universally better. Do not infer speed from scripted responses.
Completion counts mix cases and are descriptive; they are not a controlled ranking.

## What the measurements mean

- Worker and reviewer tokens/costs and their combined totals come from the saved
  accounting ledger, including retries, probes and retained reservations. Planner
  and coordinator totals remain separate, with an all-role total only when all
  role counts are known. Reported token subsets are not added again.
- JSON request evidence breaks out retained calls, probes, failures, unreconciled
  calls and cost provenance for each role. It is not a complete request inventory
  when history was truncated. Provider-reported, estimated and uncertain costs
  remain distinct; none is a billing receipt or a current price lookup.
- Elapsed, provider, cooldown, operator-wait and controller seconds reuse existing
  run timing. They measure active runs, not wall time between stopped runs. Missing,
  active or truncated timing is unavailable. Request time includes network latency.
- Check approval requests and Resume counts reuse existing instrumented metrics.
  Guidance and user follow-ups count retained `steer` and `user` events; they may
  include normal task interaction, not only rescue. Do not sum these overlapping
  categories into an invented intervention score.
- Read observations count retained successful `read file` and `read url` events
  with content. A repeated read has the same source, excerpt and item/run ownership.
  Fetch timestamps do not create new observations; changed content or another item
  does. This excludes other evidence tools and does not judge whether rereading
  was necessary. Duplicate event IDs count once.
- Repair observations include retained `repair_attempt` events, reviewer
  `REQUEST_CHANGES` decisions and failed check runs separately. These overlap and
  are not added into one repair score. Observed check repair cycles close when a
  failed command next passes in the same item, directory and follow-up scope;
  repeated failures keep one cycle open. Observed review repair cycles start at
  a repair attempt or request for changes and close at approval in the same scope.
  A different item or follow-up cannot close an earlier cycle. Open cycles remain
  visible. These are temporal observations, not proof that a particular edit
  fixed the defect or that the task is complete. All event-based measurements are
  retained-history lower bounds, so they have no exact efficiency deltas.
- Completion is either an operator assessment with an evidence fingerprint or an
  existing benchmark assertion. It is separate from controller approval, human
  acceptance and merge. Unknown completion stays unknown, even after an approval.

The export allowlists identifiers, fingerprints, classifications and numbers. It
omits prompts, model names, endpoint URLs, filesystem paths, source content,
reasoning, raw tool results and credentials. Evidence kind is explicit and declared
by the manifest; a saved task alone cannot prove that a provider was a real model.
Do not use these unsigned local observations as public Club metrics.

## Reuse scripted controller benchmarks

Existing `scripts/task_metrics.py --benchmark --output ...` exports can be read
without rerunning them. Use `kind: "scripted_controller"`, `source` pointing to the
export and `fixture_id` such as `f03`. Provide the same case/variant/repeat and
contract fields. The fixture's pinned `baseline_sha256` overrides the source and
requirements fingerprints, and `verified_outcome` supplies scripted completion.
Other contract fingerprints must still be captured. Use different saved benchmark
exports for the two variants. Synthetic usage and successful fixture assertions
validate controller behavior; they provide no real model quality, latency or
billing evidence. Scripted and recorded model trials never form a comparable pair.

The original store export and benchmark commands remain available; see
[task metrics](task-metrics.md). Tests use tiny saved dictionaries and temporary
JSON files rather than running new agent/Git workflows or live providers.
