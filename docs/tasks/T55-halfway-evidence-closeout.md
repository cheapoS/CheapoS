# T55 — Close the reliability follow-ups with honest, focused evidence

Status: Not started
Priority: Medium
Depends on: T49–T54
Size: S/M
Planning baseline: `4b6ed68`, September 14, 2026

## Outcome

The next operator receives a concise record of the repaired behaviors, remaining
limitations, and the actual evidence for the five-task milestone. “It completed”
and “we measured its full cost and reliability” remain separate claims.

## Evidence to inspect

Read the completion records for T49–T54 and the retained
[five-task report](../trials/unattended-10-tasks/RESULTS.md). That report currently
lists 327 worker turns, 60 reviews, an estimated 445 requests, and $0.019 configured/
reported cost. Treat these as reported values until their provenance is established;
do not promote the pasted assessment's superlatives into measured findings.
The underlying trial repository or private records may no longer be available.
Missing evidence is a limitation, not permission to invent replacement data.

## Work

1. Assemble a small completion matrix: requirement/defect, implementation commit,
   focused regression evidence, browser evidence where applicable, and open issue.
   Reuse unchanged passing checks from each card instead of rerunning all modules
   because the work is being summarized or merged.
2. Reconcile historical totals from existing retained records where possible.
   Distinguish worker turns, tool calls, review cycles, logical requests, and
   actual network attempts. Identify which app revision each task used and mark
   runtime repairs/restarts and planning assistance as interventions.
3. Qualify the cost statement: separate configured estimates, provider-reported
   charges, uncertain reservations, and any independently verified billing. T50
   fixes future fallback accounting; it cannot recover unrecorded historical
   requests. Never silently replace an unknown amount with zero or claim a
   precise total from incomplete data.
4. Remove or qualify conclusions not supported by those records: universal
   streaming stability, comparative “best-in-class” performance, an exact savings
   ratio, and request-quota conclusions based only on the 445-call estimate.
   The trial used priced model IDs, so a free-pool allowance comparison needs its
   own verified access basis. No account/network lookup is needed to label the
   existing conclusion unverified.
5. Retain the original trial observations and append dated corrections rather
   than rewriting unsuccessful or assisted attempts as clean autonomous runs.
   Distinguish worker-authored checks from independent acceptance and actual
   merge receipts. If a claim lacks an artifact, say so.
6. Record the next smallest optional live trial, if useful, as a proposal only.
   It requires the operator's explicit access/spending scope before dispatch,
   uses measurement mode, and measures verified completion and interventions.
   Do not automatically run Tasks 6–10, retry the deferred T44 exporter, buy
   credits, or enable paid fallback as part of this closeout.

## Acceptance

- T49–T54 have specific implementation and validation records, with browser gaps
  visibly pending rather than disguised as passes.
- Historical numbers are labeled by evidence source and uncertainty. No new
  claim of audited billing or universal model reliability is introduced.
- Known fixed bugs and unresolved limitations have distinct entries and links.
- The final handoff recommends one next experiment without launching it.

## Focused validation and handoff

Documentation-only selection: inspect links, examples, references and
`git diff --check`. Reuse retained measurements; do not add runtime tests or rerun
the five-task trial to write a report. If analysis reveals a new code defect,
document a separate bounded task rather than making an unreviewed engine patch
inside this card. Commit the evidence update and summarize what is proven.
