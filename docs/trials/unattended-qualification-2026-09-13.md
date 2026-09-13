# Live unattended qualification — September 13, 2026

This follow-up uses a disposable label-normalization project, real free remote
models through the existing OmniRoute configuration, and the production branch
controller. It does not modify the unfinished report-export feature from the
previous trial or use personal task history as an execution fixture.

## Acceptance and boundaries

One item must create `labels.py`, amend an existing `README.md`, pass four
prewritten independent `unittest` tests without editing them, submit a checkpoint,
receive a distinct model's review bound to the candidate, and reach final
readiness through a controller-created feature commit. No merge or push is part
of the trial. The observer uses the operator-facing controller services directly;
this is not a browser/UI acceptance test.

Task storage and the source fixture are separate under
`/tmp/cheapos-live-qualification-20260913`. The operator supplied the baseline
specification and tests, but did not write the requested implementation.

## Planning observations

- Initial live plan `8d5e93c315a24e1d87e9281851a438a8` treated prose beginning
  with `List` as a verification command and reached a setup-blocked draft.
- The app repair validates command syntax and executable availability during
  the existing bounded planning-repair loop. Feedback identifies the exact
  item/field/index. Unavailable setup still retains the complete blocked draft
  after repair attempts; no command is executed and no authority is granted.
- The subsequent live proposal `8187cd076e594d519e330e0648560f8c` contained
  executable commands but split one requested item into four and included
  meaningless completion checks. The observer rejected that proposal and
  replaced it through `reprepare` with one item and the supplied actual test
  command. Original planning accounting was retained.
- Prompt guidance now explicitly keeps implementation/tests/checkpoint together
  and asks for exact supplied commands. This alone did not make the observed
  model obey item-count or semantic-check requirements. Planning remains assisted.

## First execution

Run `8187cd076e594d519e330e0648560f8c` created the implementation, updated the
README and passed all four tests, without operator prompts after Start. It then
paused before independent review because the observer's 12,000 reviewer-token
allowance could not fit the evidence packet plus reserved response. Only 303
reviewer tokens had actually been used; reservation requirements also matter.
This was an inadequate trial budget, not an autonomous success or a model stall.
No feature commit resulted.

A separate second execution uses the same one-item proposal with a 40,000-token
review allowance, preserving the failed attempt. Both use a $0 estimated cap,
20 worker turns, 40 requests, 600 working seconds, and a 30-second check limit.
There is no paid/local fallback or turn-limit increase. Saved cost accounting
is not an independent provider billing receipt.

## App repair validation

Ten planner tests passed, including field-specific repair of prose and shell
commands. Seven HTTP planning tests passed in 19.445 seconds, including retained
blocked drafts, repair accounting, explicit Start, cancellation and captured
prompt/document inputs. The planning-race regression also passed. No full suite
was run for this focused repair.

## Successful qualification

**Run `d5e2e950b34140dca0c6d9426e32b9ac` reached `ready_for_merge`.**
The operator prepared its one-item proposal and approved Start. From that point,
there were **zero operator prompts, edits, resumes or repairs** in this run.

| Evidence | Result |
| --- | --- |
| Worker | `openrouter/cohere/north-mini-code:free` |
| Independent reviewer | `openrouter/nvidia/nemotron-3-super-120b-a12b:free` |
| Elapsed execution | 109.116 seconds |
| Provider request time | 91.632 seconds |
| Worker turns / total requests | 7 / 15 |
| Accounted worker / reviewer tokens | 23,786 / 28,882 |
| Accounted cost | $0.00, estimated; zero uncertain reservations remaining |
| Real checks | Four tests passed at item verification and again at final verification |
| Feature commit | `56d9d881f7aaf58513c66f30a4f7ad0206a877e8` |
| Feature branch | `feature/labels-v2` in the disposable project |
| Final readiness | Independent final review passed; fresh merge preview reports available |

The observer independently checked that the completed commit receipt matches
the run and item, source `main` remains at the baseline, the source working tree
is clean, and the only committed changes are `labels.py` and `README.md`.
`test_labels.py` is byte-for-byte unchanged in the task copy and unchanged in
the feature commit. The implementation and README were written by the worker,
not supplied by the observer. No merge or push was performed.

Machine-local summary: `/tmp/cheapos-live-qualification-20260913/qualification-result.json`.
The earlier unsuccessful records remain separate in the same isolated storage.

## What this establishes and what remains

The production execution controller can take this small real-model task from
Start through new-file creation, existing-file modification, passing tests,
independent review, a feature commit and final readiness without intervention.
It does **not** establish autonomous planning, reliable completion of a larger
feature, or automatic recovery from an ineffective worker. The larger Markdown
report-export feature remains unimplemented by this trial. Its next attempt
should use focused checks under the current validation policy and retain clear
separation between operator-assisted planning and autonomous execution.
