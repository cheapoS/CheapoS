# T55 — Close the reliability follow-ups with honest, focused evidence

Status: Done
Priority: Medium
Depends on: T49–T54, T56–T60
Size: S/M
Planning baseline: `4b6ed68`, September 14, 2026

## Outcome

The next operator receives a concise record of the repaired behaviors, remaining
limitations, and the actual evidence for the five-task milestone. “It completed”
and “we measured its full cost and reliability” remain separate claims.

## Evidence to inspect

Read the completion records for T49–T54 and T56–T60 and the retained
[five-task report](../trials/unattended-10-tasks/RESULTS.md). That report currently
lists 327 worker turns, 60 reviews, an estimated 445 requests, and $0.019 configured/
reported cost. Treat these as reported values until their provenance is established;
do not promote the pasted assessment's superlatives into measured findings.
The underlying trial repository or private records may no longer be available.
Missing evidence is a limitation, not permission to invent replacement data.

The later pasted review-loop assessment lists 13, 11, 4, 3 and 15 decisions for
Tasks 1–5: 46 total (16 REQUEST_CHANGES and 30 APPROVE). Its headline still says
60 reviews; the earlier report instead lists 13, 16, 4, 3 and 24. Preserve those
source distinctions until records explain them. Do not assume one count is wrong
or silently relabel model requests as substantive review decisions.

## Work

1. Assemble a small completion matrix: requirement/defect, implementation commit,
   focused regression evidence, browser evidence where applicable, and open issue.
   Reuse unchanged passing checks from each card instead of rerunning all modules
   because the work is being summarized or merged.
2. Reconcile historical totals from existing retained records where possible.
   Distinguish worker turns, tool calls, review cycles, logical requests, and
   actual network attempts. Identify which app revision each task used and mark
   runtime repairs/restarts and planning assistance as interventions.
   Separate item decisions, final chunk decisions, final synthesis, schema
   corrections, context reads, transport retries, and worker repair cycles.
   Use T50/T60's event distinctions for future counts. If historical records
   cannot resolve the 46-versus-60 discrepancy, label it unresolved explicitly.
   Measure repair turns and repeated disputes only where evidence supports that
   attribution; do not carry forward the unsupported claim that 80% of loops
   came from one edit failure mode.
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

- T49–T54 and T56–T60 have specific implementation and validation records, with browser gaps
  visibly pending rather than disguised as passes.
- Historical numbers are labeled by evidence source and uncertainty. No new
  claim of audited billing or universal model reliability is introduced.
- Review requests, valid decisions, and actual repair cycles are distinct. The
  46-versus-60 discrepancy is reconciled from evidence or explicitly unresolved.
- Known fixed bugs and unresolved limitations have distinct entries and links.
- The final handoff recommends one next experiment without launching it.

## Focused validation and handoff

Documentation-only selection: inspect links, examples, references and
`git diff --check`. Reuse retained measurements; do not add runtime tests or rerun
the five-task trial to write a report. If analysis reveals a new code defect,
document a separate bounded task rather than making an unreviewed engine patch
inside this card. Commit the evidence update and summarize what is proven.


## Completion record — September 14, 2026

Implementation: `e0fcc51` (with foundations `abe2545`, `226b604`, `3b48cef`).

Reconciled the five selected saved task records with retained trial Git history in docs/trials/unattended-10-tasks/RESULTS.md, appending dated corrections. Stored counters total 60, while valid decision events total 56 (41 approvals/15 rejections); the pasted 46-decision table remains unmatched. There are 465 dispatched records, not proof of exact network attempts. Recorded cost is not audited billing; failed additional attempts and runtime interventions remain visible. CLI has a Git merge but no completed app merge receipt in its saved paused task. Exact per-request app revisions were not retained. No historical approvals were requalified and no new live trial was launched.

The completion matrix in docs/development/review-correctness.md links implementation and focused validation. Browser gaps are listed explicitly. Documentation links and git diff --check were checked; unchanged runtime checks were reused. One optional measured two-item follow-up is proposed, with access/spending approval required before dispatch. T44 and Tasks 6–10 remain deferred/proposed.
