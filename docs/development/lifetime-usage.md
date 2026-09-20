# Lifetime Usage & savings

The bottom-left **Usage & savings** entry opens that page in Settings
without leaving the selected chat. **The Cheapskate Club** has its own Settings
page for account connection, sharing preferences, and sync across this installation.
Usage charts and local exports remain in **Usage & savings**.
All time is the default; seven-day and
30-day filters use UTC dates. Only recorded dates appear in history; missing
history is not a zero-usage day. Daily display is bounded to 366 recorded days.

Reported input and output tokens lead the summary. Local, public-free remote,
included-account, paid/metered, and unknown access are separate. A zero configured
price does not prove public-free access. Saved dispatch evidence determines the
category; a reported charge on a free route is counted as paid usage and flagged.
Requested/served identity disagreements remain unknown. Free share uses classified
free-plus-paid remote reported tokens; local, included and unknown are excluded.

Reasoning and cached counts are subsets, never extra tokens. Missing subset
coverage is shown. Reservations, configured estimates, provider-reported cost,
and undated historical accounted totals remain separate. Sub-cent costs remain
visible. These totals are not billing receipts, and local hardware/electricity
and account subscription costs are outside this accounting.

The versioned `lifetime-usage.json` ledger is private to the application data
folder. Task saves incrementally reconcile stable hashed task/request identities;
unchanged accounting avoids a disk write. Atomic replacement leaves the previous
ledger intact if writing fails. On startup saved task records backfill retained
evidence. Capped history contributes only its residual accounted totals, without
inventing historical access categories or double-counting recorded requests.
Historical startup greetings may be missing; future greetings and compatibility
requests are recorded with the same accounting rules. Scripted/demo requests are
excluded. No personal data store was migrated during development verification.

Archiving, Trash, restoration and source-task deletion do not remove already
recorded usage. Retained statistics omit prompts, paths, task titles, outputs and
credentials. Summary reads are cached until accounting changes and never scan
all task files on a UI poll. Human-accepted Interactive jobs and merged runs are
separate distinct-job counts; item commits are not extra completed jobs.
Independent review is displayed separately from human acceptance.

**Export summary** previews Markdown or JSON before an explicit local download.
It exports the selected period, categories, roles, costs, coverage, completion
definitions and app version. It does not upload, publish or modify the README.
There is no savings multiplier: free tokens used do not establish tokens saved.
A defensible comparison needs comparable outcomes and a measured baseline.
