# Limits & recovery

Open Settings, choose **This chat**, **Project overrides**, or **App defaults**,
then **Limits & recovery**. Defaults only affect future chats. Project overrides
are optional. Each value shows its source; existing chats retain their captured
policy. Saved legacy values are preserved. New installations have no cumulative
work caps and use free/included remote routes.

Use **No work caps**, or enter individual cumulative budgets. Blank work fields
mean **No cap**; zero is an explicit zero allowance. Requests include failed and
retried dispatches across roles; tool attempts are separate. Checkpoints count
recorded checkpoint reviews, including pending reviews; inspection turns do not count. Raising a
100-request cap to 150 after 100 requests gives 50 additional requests.

Per-operation controls are separate. Blank means **Automatic**. Output uses
current catalog capacity where available, otherwise a conservative estimate.
Unknown or stale capacity is never described as unlimited. Explicit output caps
remain binding. The request deadline defaults to the transport's normal deadline;
verification Automatic starts from the saved check deadline and increases it
using that exact command’s observed durations and timeouts. Cancellation, work
budgets and bounded output storage remain enforced.

Pause active work before applying settings. For paused work, **Apply & continue**
uses the existing saved continuation. Counts, reservations, permissions, review
findings and candidate-bound checks remain intact. Model pins, spending limits,
command grants and final merge approval are independent of work budgets.

Recovery changes strategy after malformed output, reduces oversized request
context with retained references, or finds another authorized route after an
outage. A real missing prerequisite or exhausted operator budget still needs a
specific operator decision. No cap never means infinite provider capacity or
permission to use paid models.
