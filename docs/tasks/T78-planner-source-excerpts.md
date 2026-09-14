# T78 — Planner source excerpts and accurate response diagnostics

Status: Complete, September 14, 2026
Depends on: T65, T73
Size: S

## Observed failure

The planner's source-inspection tool reused the complete task-document reader.
It rejected files larger than 64,000 bytes, including cheapoS's 91,480-byte
stylesheet and 150,634-byte frontend script. The observed planner then returned
ordinary text asking the operator for file contents. Responses finished normally;
they were neither truncated nor multiple proposals. A shared parser error
incorrectly described them that way, and repair requests omitted the rejected
plain-text answer. Repeating the task could reproduce this defect but did not
cause it. These observations came from retained local responses; no new live
inference was needed for diagnosis or validation.

## Delivered behavior

- Source inspection uses the existing 256,000-byte workspace text ceiling and
  returns excerpts capped at 12,000 characters. Normal reads also cover at most
  200 lines. Optional literal queries locate symbols/selectors deeper in a file.
- Results identify the full-file hash, source byte count, excerpt coordinates,
  omitted content and continuation coordinates. Column-aware continuation works
  inside long/minified lines and across CRLF and Unicode text. Missing query
  matches are explicit. An explicit end line bounds a query's excerpt too.
- Selected task documents still require a complete capture within 64,000 bytes;
  specifications are never silently truncated. Both paths share descriptor-based
  reads with file-name, path traversal, symlink, regular-file and UTF-8 checks.
- Planner guidance explains search/continuation rather than asking the operator
  to paste readable source. The inspection schema and dispatcher accept the
  optional range/query fields. Discovery remains limited to six requests.
- Missing calls with plain text, empty replies, multiple calls and explicit
  output-limit responses have distinct app-authored diagnoses. After the existing
  two repairs, the final planning pause retains that diagnosis through public
  serialization. Arbitrary response content is not copied into the banner.
- Repairs retain up to 12,000 characters of the rejected plain-text answer and
  require a proper proposal or clarification tool call. Plain text never creates
  a plan. Explicitly truncated inspection calls are not dispatched.

## Validation

47 distinct focused Python cases passed:

- `python3 -B scripts/dev_tests.py --pattern test_branch_planner.py --timings`:
  22 cases, 1.748s.
- `python3 -B scripts/dev_tests.py --pattern test_branch_planning_http.py --pattern test_branch_planning_race.py --pattern test_planning_allowance.py --pattern test_branch_pause.py --jobs 4 --timings`:
  25 existing cases, 27.318s. Most time was in existing HTTP/Git fixtures.
- `git diff --check` passed. Direct read-only inspection of the actual stylesheet
  and script returned valid 12,000-character excerpts without the old 64 KB error.

Seven new tests use small temporary files and scripted/mocked planner responses:
about 10ms combined, each under 3ms including setup/teardown. They cover large
source discovery through the real dispatcher, normal proposal validation after a
plain-text repair, exact continuation, source access restrictions, unchanged
complete-specification limit, bounded repair context, no truncated dispatch, and
accurate public pause explanations. No new Git workflow, server or timed wait was
introduced. They run when the existing planner test module is selected.

The static selector expands this module through the engine to 78 test modules.
The focused planner, HTTP, race, allowance and pause modules were selected
explicitly instead; this change does not affect general worker execution or Git
commit logic. No full suite or new browser test was run: rendering is unchanged,
and the existing public pause serializer was exercised directly.

## Limits and rollout

This is deterministic regression evidence, not a live-model completion claim.
The planner still needs to choose relevant excerpts and produce a valid proposal.
Files beyond the workspace byte ceiling still return a bounded read error.
Discovery, repair, model, spending and execution-approval limits are unchanged;
the fix does not automatically restart or reauthorize failed personal runs.
Backend changes take effect on the next server restart; do not interrupt active
operator work just to reload them.
