# Usage and bounded concurrency validation — T79–T81

Implemented in the isolated `work/pending-tasks` worktree from `162d2f9`.
The running application and its personal data were untouched. No restart or live
inference was used. T81 was developed first; the operator explicitly selected the
previously deferred T79/T80 cards for this batch.

## Focused checks and test cost

The initial changed-file plan was empty. Once changes existed the import-based
selector selected 82 Python modules through shared engine/storage imports. We
used focused feature, permissions, transport, persistence, Git and recovery
coverage instead of running the full suite during iteration.

- 158 frontend cases passed in 108.54 ms, with JS syntax and diff checks.
- Four new pure lifetime persistence/aggregation cases passed in 0.008 s.
  Mixed access/roles, failed and missing usage, reservations, reconciliation,
  duplicate import, truncation, privacy and atomic replacement are covered.
- Two new storage/GET integration cases use only a temporary directory and direct
  handler invocation. Together with the four ledger and four existing metric
  cases, ten cases passed in 0.009 s. No sockets, inference or Git fixture.
- Ten new Node cases for summary loading/filter races/export and submission
  ownership ran in 82.29 ms separately. No browser test framework was added.
- Four new deterministic admission/resource cases passed in 0.019 s. A real
  budget ledger exercises contention and release after bookkeeping failure.
- The existing planner-race fixture was extended to run an Interactive read and
  response while a planner waits on an Event barrier. It adds under 0.3 s to the
  existing fixture and no new Git setup. This plus admission passed in 0.336 s.
- Existing startup accounting tests: 17 passed in 0.246 s. Earlier focused
  accounting/failed-response dispatch checks: eight passed in 0.014 s.
- Existing branch start (3), commits (9), and cooldown (8) modules passed;
  representative batch including admission/planner ran in 14.138 s.
- Existing branch merge: seven passed in 17.380 s. Final completion/reconciliation:
  six passed in 33.396 s. Transport and metadata/Trash focused checks passed.
  Lightweight test harnesses now initialize the actual admission component;
  expected blocker wording changed without weakening rejection assertions.

No new full agent/Git workflow, benchmark collection, deliberate sleep or live
provider test was introduced. Existing slower integration fixtures were reused.
Passing unchanged checks were not repeated for the merge itself.

## Browser evidence

The lifetime view was opened from a synthetic saved chat on a dedicated fixture
port. It showed 1,750 reported tokens, 150 public-free tokens, 450 paid tokens,
25% classified free share and $0.003 accounted cost. Seven-day filtering and
Markdown preview preserved those fixture totals and reported the actual version
and coverage. Closing returned to the same selected chat. The export contained
no task prompt/path/title. Loading/error/retry and stale-filter responses also
have controlled Node coverage.

A separate synthetic submission fixture showed the specific **Saved, not started**
blocker, disabled Send, and Enter retaining the draft. After capacity became
available, Retry started the same saved task. Guidance cleared only its owning
draft; switching to the other conversation preserved reviewer activity. Both
Interactive and Unattended sidebar indicators were active simultaneously. These
are synthetic UI checks, not a live-provider qualification. Sample/demo starter
buttons also use the same admission gate. Narrow-window visual behavior relies
on the responsive layout; it was not separately exercised in this browser pass.

## Boundaries and retained safeguards

Admission permits one Interactive and one Unattended runtime, including planning
reservations. A third request is rejected explicitly, not queued. One live runtime
per task remains enforced. Waiting for local inference or checks is cancelable,
does not consume model requests, and does not refill existing allowances.

Repository integrations share a lock based on Git common-directory identity,
including linked worktrees; unrelated repositories have separate locks. Expected
refs, clean checkout, exact reviewed content and explicit integration authority
are still validated. Conflicting task mutations are blocked during integration.
Shared gateway cooldown and probe coalescing retain their existing locks.

Historical accounting cannot recover usage that was never saved. Undated legacy
residuals remain unknown and are excluded from date filters. Summary/export
makes no achieved savings claim and never authorizes paid fallback. No live
quality qualification was performed. The current stress-test app keeps its
existing process; these changes take effect on a later operator-chosen restart.

The refreshed UI tolerates a still-running older server: an unavailable admission
endpoint preserves the legacy single-task rule and leaves Chat usable. Other
capacity-fetch failures fail closed without replacing the application with a
startup error. Lifetime statistics on an older server explain that they become
available after a later restart; no restart is triggered. This matters when
merging static assets while an operator's long-running task remains active.

## Follow-up: usage button asset delivery

The initial browser mock did not enforce the real server's static-file allowlist.
The usage JavaScript and CSS were missing from that allowlist, leaving the button
inert in the actual app. Both explicit assets are now allowed; the allowlist stays
closed to other files. The existing HTTP test discovers the page's script/link
assets and verifies actual GET delivery, plus HEAD for the usage files. It and
the same-origin rejection check passed in 0.042 seconds, without a new fixture.
Activating this server-code fix requires a Python server restart, not just the
Restart webapp page reload. No running application was restarted for this repair.
