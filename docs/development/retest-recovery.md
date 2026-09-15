# Retest-loop investigation and fixes

## Observed failure

The saved backend-restart run had 48 verification records. Its last 12 records
ran the same HTTP unittest command against the same patch and verification
identity, and all passed. Those 12 runs took about 258 seconds; the 11 redundant
runs accounted for about 236 seconds. Different unittest elapsed-time lines
made otherwise identical output look like new progress.

Review had started twice. A malformed tool call, model handoff, repeated reads,
and finally the cumulative request allowance interrupted it. Resume discarded
pending review evidence and restarted the worker even while the item remained
in the reviewing stage. The worker then ran the passing tests again. The saved
run ultimately consumed its 196-request allowance; passing tests did not mean
that independent review had finished.

## Corrected behavior

- Unattended workers reuse the latest complete successful check only when the
  exact command, current files, workspace generation, Git baseline, runner and
  environment/configuration identity still match. Failed, incomplete, stale or
  truncated checks are not reused. Reuse does not invent another execution or
  consume another test-duration entry.
- If an unattended worker repeats that unchanged passing check, the controller
  submits the saved implementation for independent item review. It waits until
  the end of the tool batch, and does not substitute for required worker repair
  dispositions. The reviewer still checks every requirement and may reject it.
- Interactive explicit test requests retain their execution and permission
  behavior. Checkpoint evidence reuse remains available in both work modes.
- Successful test-output timing differences no longer count as progress.
  Changed verification identities and failure diagnostics still do.
- Resume continues an interrupted item review directly. Completed reviewer
  tool exchanges and validated repair dispositions survive a restart, bounded
  to 60,000 characters of whole exchanges. The candidate packet is rebuilt and
  checked; history from a different candidate is discarded. Incomplete tool
  exchanges are never replayed.
- Existing review/recovery counters and disagreement records survive Resume.
  Coaching accounts for failed requests before the last permitted review call.
- Unittest target normalization handles `tests/test_http.py` without rewriting
  executable paths, absolute paths, discovery options or `-k` filters.
- Command-approval clicks show immediate pending feedback, reject duplicate
  submission, and expose errors inline. The unattended permission-renewal
  dialog closes on submission, with continuation progress in Chat. Server
  authorization remains authoritative; the UI does not claim acceptance early.

## Review of the incoming edits

Retained the intent of the unittest target fix and stage-aware guidance after
passing checks. Corrected their handling of executable/discovery paths and
verification freshness. Removed blanket recovery/handoff resets and deletion of
saved review evidence. Did not repurpose the worker checkpoint interval as a
reviewer request allowance, or clear a limit diagnostic without fixing its cause.

## Validation and cost

Change-scoped verification covered 73 distinct Python cases across verification,
branch evidence, independent review, disagreements, progress recovery, worker
policy, execution context, permissions, work limits, branch restart recovery and
branch execution. The initial pass caught Interactive command-reuse regressions;
the unchanged permission assertions passed after restricting the new automatic
reuse to Unattended. The final affected subset passed 30 cases in 140.7 seconds;
most time came from existing multi-item/Git fixtures. Those fixtures were not
new tests and are not a new full-suite requirement.

The eight new deterministic Python cases ran in 0.004 seconds. Three new
JavaScript cases use unresolved promises to check pending feedback, modal
closure, duplicate prevention, errors and chat switching, without real waits.
All 181 frontend cases passed in about 0.12 seconds, plus syntax and diff checks.
No new heavy regression fixture was added.

Computer-use validation used a disposable repository, isolated app state, and
scripted zero-cost providers. Holding approval responses confirmed immediate
inline feedback and modal closure. Releasing the unattended response led to
one worker turn, reused item verification, independent approval, one item
commit, and `ready_for_merge`. There were two actual check records: the original
saved item check and final integration verification after the Git baseline
changed. This establishes controller/UI behavior, not live provider reliability.

The personal run's files, models, spending policy and exhausted request
allowance were not edited to make the demonstration succeed. It needs an
explicit allowance decision before additional inference; a restart does not
refund already consumed requests. The implementation is already present on main
from the earlier backend-restart commit, so that task must also inspect current
project state before any eventual integration.
