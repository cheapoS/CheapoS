# Long task refresh performance

Long runs retain their complete saved activity and review evidence. UI polling
should not repeatedly copy or transfer that history when nothing has changed.

- Sidebar presentation reads titles and change counts under the store lock
  without deep-copying execution records. Returned summary dictionaries remain
  independent of worker-owned state.
- A full task GET includes an opaque `ETag`. The browser sends that value on
  subsequent polls; an unchanged task returns HTTP 304 with no body, skipping
  snapshot copying, public projection, JSON serialization, parsing and rendering.
- Every save and live publish invalidates the view version independently of
  `updated_at`. Metadata changes and server restarts also invalidate it. Versions
  are read-only presentation state and never change task authorization or evidence.
- Technical logs show 100 events per page. Older pages stay anchored to their
  newest saved event while new output arrives. Latest events returns to the live
  page. Paging does not remove any stored events or review evidence.

Changed task snapshots still contain the full public task record. This is an
initial reduction in repeated work, not incremental event streaming or a new
persistence format. Whole-record saves and long Chat histories remain potential
follow-up profiling targets.

## Measurements and validation

Read-only diagnosis on September 17, 2026 found a long task with about 1,200
events, a 17 MB saved record and a 10 MB public task response. Its open Technical
logs view contained about 13,500 elements. A live sidebar GET took 945 ms.

On the same in-memory snapshot of 78 saved tasks, sidebar presentation went from
794 ms to 3.2 ms and returned identical data. An unchanged store poll took
0.109 ms and required no task payload. These are single local measurements, not
latency guarantees. A synthetic 1,200-event log rendered 100 event rows instead
of 1,200; markup generation went from 3.21 ms to 0.41 ms.

Validation used disposable fixtures and no model requests:

- All 278 JavaScript tests passed, including pagination, unchanged polling,
  timestamp-independent revisions, normal errors and stale-response protection.
- Five new offline polling tests took 0.019 seconds together. Three new
  JavaScript cases took approximately 0.004 seconds together.
- Existing metadata, trash, and focused HTTP metadata/bootstrap/origin checks
  passed (16 Python cases including the five new polling cases).
- A disposable browser fixture verified older/latest navigation, an unchanged
  HTTP poll preserving an open detail, and new output preserving the older page.
- The existing branch-storage test
  `test_manual_mutations_cannot_change_branch_contract` fails with `KeyError:
  'limits'` on both the unchanged baseline and this branch. Its fixture predates
  the current limit-update behavior; this performance change does not alter it.

Useful focused commands:

```sh
PYTHONPATH=.:tests python3 -B -m unittest tests.test_task_polling tests.test_task_metadata tests.test_task_trash
node --test tests/*.js
python3 -B -m unittest tests.test_http.HTTPTests.test_metadata_routes_share_titles_and_filter_history tests.test_http.HTTPTests.test_bootstrap_and_static_files_without_signin tests.test_http.HTTPTests.test_cross_site_and_dns_rebinding_blocked
```
