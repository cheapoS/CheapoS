# T81 — Lifetime Usage & savings, with shareable evidence

Status: Ready — near-term priority; implement when selected
Depends on: Existing T24 metrics and role-separated accounting; not T79/T80
Size: M — ship durable totals and the summary first, then history/export polish
Evidence: September 14, 2026, 4:21 PM operator request and account-stats screenshot;
source inspected at `3cf19a6`.

## Outcome and product direction

Per-chat totals do not show the value of using cheapoS over weeks. Add a
**Usage & savings** button near the bottom of the left sidebar, accessible from
Home and every chat. It opens a readable app-wide summary without needing an
account or losing the current conversation. This is local installation usage,
across projects and Interactive/Unattended work, not the provider account's
entire usage or activity from other tools.

The operator clarified the goal: **use fewer paid tokens by doing more work with
free models**, not necessarily reduce total tokens. Prioritize the free versus
paid totals and their share over a hypothetical savings calculator.

Lead with lifetime model tokens, free-model tokens, paid-model tokens, and
accounted API cost. Show local and included-access usage separately so those
tokens remain visible without being mislabeled public-free. Use a simple stacked
breakdown and large readable figures. Explain unknown coverage beside the figures.
The supplied screenshot is inspiration for cumulative statistics, not a request
for login, streaks, plugin tracking, or copying its numbers.

A small top-right shortcut may show the same lifetime summary if it fits without
crowding task controls. Label it **Lifetime** so it cannot be mistaken for the
active chat's usage. The bottom-left entry is the primary first implementation;
do not block delivery on choosing both locations.

## Read first

- [Task metrics and current limitations](../development/task-metrics.md) and
  [T24](T24-completion-metrics.md): input/output totals, token subsets, provenance,
  anonymized export, and the removal of unsupported savings claims.
- `cheapos/metrics.py`: `record_usage()`, `aggregate()`, `export()`.
- `cheapos/providers.py`: `reserve()` and `reconcile()`; `cheapos/engine.py`:
  request metrics, failed-response accounting, and history truncation.
- `cheapos/branch_budget.py`: branch consumption already observes task requests;
  adding both task usage and branch consumption would count the same work twice.
- `cheapos/storage.py`, `cheapos/startup.py`, `scripts/task_metrics.py`, and
  `cheapos/server.py`: persistence, greeting accounting, exports, and public data.
- `dist/app.js`: the existing per-task usage pill and inspector; sidebar markup
  in `dist/index.html`. Keep the current task totals useful alongside the new view.

## Implementation increments

### 1. Define truthful totals and a durable local record

- Persist a versioned usage summary/ledger at the application data-store level.
  Record the coverage start date and last update. App restart, selecting another
  project, archiving, trashing, or restoring a chat must not reset lifetime totals.
- Include coordinator/local chat, planner, worker, reviewer, compatibility probes,
  retries, and failed/cancelled requests when usage was actually reported. Audit
  requests outside task storage, such as startup greetings. Record them going
  forward; disclose any historical gaps rather than inventing prior usage.
- Separate **reported tokens** from estimates and outstanding reservations.
  Reasoning/cached tokens are subsets where the provider defines them that way;
  never add them again to input/output totals. Missing values stay unknown.
  Demo/scripted usage must not contribute to real usage or savings highlights.
- Classify each request using its saved, request-time route/access evidence:
  public-free remote, local, included account access, paid/metered, or unknown.
  Do not infer public-free from a configured price of zero. Preserve requested
  versus served identity where available; missing or conflicting evidence must
  remain visible. Current settings or today's catalog must not rewrite history.
- Track monetary provenance separately: provider-reported cost, configured-price
  estimate, and unresolved reservations. A nominally free route reporting a
  charge contributes that charge and shows the mismatch; it must not inflate a
  claim of free usage. Keep costs below one cent visible in Details/export.
  Local means no API charge, not zero electricity/hardware cost. Included access
  may have subscription cost outside this app's accounting.
- Make request recording/reconciliation idempotent with stable identities.
  Repeated saves, polling, retries, crash recovery, or rerunning migration must
  not count a request twice. A reconciled result replaces its reservation; it
  does not add to it. Distinct dispatched retry requests still count separately.
  Commit aggregate state atomically and recover incomplete updates safely.
- Backfill existing saved history once using evidence already retained. Request
  history is capped; where only task totals remain, retain those as accounted
  historical totals with unknown classification/coverage. Do not guess the split
  or mix historical totals with overlapping request records. Show **Recorded
  since [date] · partial earlier history** when appropriate.
- Keep only deidentified usage aggregates needed after permanent chat deletion;
  do not retain deleted prompts, file paths, or model output for statistics.
  Explain this retention in the view. The feature does not add automatic uploads,
  chat deletion, or a destructive reset workflow.

### 2. Make the lifetime summary easy to read

- The sidebar entry opens promptly with loading/error/retry feedback; fetching
  history must not freeze chat or require scanning every task on each UI poll.
  Keep aggregates incremental and history queries bounded. Reopening is cheap.
- Show **All time** by default, an accessible free/local/included/paid/unknown
  breakdown, and exact values/provenance on inspection. Any percentage names its
  denominator and excludes unknown data only with an explicit coverage label.
  For example, **80% of classified remote tokens used free models** can use
  eligible free / (eligible free + paid), with local, included, unknown, and
  charged-free anomalies disclosed separately. The figure is illustrative;
  compute it from real recorded data, not a product target or default value.
- Add a simple daily/cumulative history view when dated evidence exists. Permit
  a recent-period filter such as 7/30 days. Missing history is a gap, not zero;
  changing timezone/grouping must not alter lifetime totals. Avoid a dense
  dashboard or streaks that reward wasted turns.
- Show completed work alongside volume where existing evidence supports it:
  human-accepted commits and merged runs, with independent-review approval kept
  separate. Reuse durable receipts and avoid counting an item commit, its final
  merge, and the parent run as three completed jobs. Failed work still consumes
  tokens; do not hide it from usage totals to improve the story.
- Preserve keyboard navigation, readable contrast, narrow-window layout, and
  the selected chat/draft/scroll state when closing. Updating statistics must
  not steal focus or interfere with an active run.

### 3. Provide a summary that can support repository claims

- Offer an explicit **Export summary** action using local Markdown/JSON, reusing
  the existing metrics export where useful. Include date range, coverage,
  category totals, role totals, cost provenance, completed-work definitions,
  app version, and any comparison methodology. A clean visible summary should
  also be suitable for an operator screenshot.
- Exclude prompts, raw logs, credentials, project paths, and identifying task
  titles. Preview what will be exported. Exporting does not publish, upload,
  edit the README, or make any inference requests.
- **Free tokens used** is the primary measured value. Never rename it **tokens
  saved**: more free tokens can reflect retries or review churn. An actual token
  reduction needs comparable task outcomes and a measured baseline.
- Do not revive the removed fixed frontier-price multiplier. A later optional
  comparison must name its baseline, date, input/output rates, scope, and outcome
  equivalence. Hypothetical cost for the same token volume is labeled a price
  comparison, not achieved savings. If no defensible baseline exists, say
  **Savings comparison not configured** and still ship the useful usage view.
- This is observation, not authorization: no model/routing changes, spending
  allowances, billing-tolerance changes, paid fallbacks, or extra provider calls.

## Acceptance and economical validation

1. A tiny mixed-record fixture reconciles totals across all four roles and access
   categories, with paid cost, a charged free route, missing usage, a failed
   request, a retry, and synthetic demo usage. Subsets/reservations do not double
   count, and unknown data is not relabeled zero/free.
2. Duplicate ingestion, reconciliation after restart, and repeated historical
   import leave the same totals. Archived/trashed/restored chats and removed
   source task files retain already recorded deidentified lifetime usage. A
   truncated legacy history reports partial coverage without inventing a split.
3. UI fixture proves opening from Home/chat, immediate pending/error states,
   filters, readable breakdown, and returning to the same chat. Summary/export
   match the fixture totals and include limitations, with no private payloads.
4. Use small deterministic aggregation/persistence cases and controlled Node
   fixtures. Reuse existing metrics coverage; do not run or duplicate the seven
   full benchmark workflows just to test a statistics view. Use disposable data,
   no real inference, account credentials, delays, or personal-store migration
   during tests. Follow CONTRIBUTING.md and report new-test timing. Any new
   heavy test needs the operator's explicit acceptance of its disclosed cost.

Completion: Not implemented. Record supported coverage, migration/retention
behavior, UI/export evidence, selected checks, test timing, and remaining gaps.
Update this card and [TASKS.md](../../TASKS.md); commit only this task's changes.
