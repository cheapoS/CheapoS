# Evidence-based approval

A passing check is necessary evidence, not proof that the requested behavior is
complete. A reviewer also needs to assess the implementation, neighboring
behavior, and whether the tests could pass with the defect still present.

## What the controller enforces

New real tasks use review contract version 1. Historical tasks and existing
approvals retain their saved contract so an update does not invalidate an
in-flight review or commit. Scripted demos and legacy fixtures retain their
original format; new follow-up tasks use version 1. Interactive checkpoints,
Unattended item reviews, packet reviews and final synthesis share the same
approval validator.

An approval supplies:

- A reason and evidence citations for each assigned criterion, using returned
  excerpt references or literal quotations.
- A separate assessment of regressions and verification coverage.
- An explicit list of verification limitations, displayed in the normal review
  message. An empty list means the reviewer reports none; it is not a controller
  guarantee that none exist.

The controller registers the actual diff, check records and returned source
excerpts. Unknown sources, fabricated quotations, missing criteria, empty
feedback, unresolved defects attached to APPROVE, and a whole-task approval
supported only by green check records are rejected. Tests and review remain bound
to the candidate. Saved receipt validation checks the candidate and assessment
binding before integration. These hashes are local integrity bindings, not
cryptographic attestation of a model's reasoning.

Reviewers receive the original request and captured planning inputs alongside the
accepted scope. A planner that omits acceptance criteria or supplies only Git
commit criteria must correct its proposal through the existing automatic repair
path. The controller no longer invents a generic criterion for those proposals.
The approved plan and explicit amendments remain the authority: historical chat
or a document is not permission to expand the work.

Each partial approval covers only its assigned evidence. Final synthesis receives
validated source excerpts from earlier reviews, rather than relying only on
APPROVE labels and echoed IDs. Large catalogs retain their complete content behind
readable references. Missing source can be retrieved before deciding; packet size
is not a new reason to stop work.

Unsupported approvals receive specific correction feedback. Repeated failures
use an eligible replacement reviewer when the task authorizes automatic selection.
Saved edits, checks, cumulative budgets, failure history and command permissions
remain in force. Manual reviewer choices do not authorize silently using a
different model. The existing REQUEST_TESTS and supported-defect paths remain
available; a formatting problem is not a reason to invent a code defect.

Citation matching accepts literal code with controller-added line-number or
unified-diff gutters omitted. It preserves code indentation, wording, diff sides,
and hunk/file boundaries. It does not accept paraphrases or combine disconnected
excerpts. Older saved read windows can use the same matching without resetting
the candidate or review history. Receipts retain the original source digest.

A rejected assessment reports its field errors together. If a quote occurs in
another already-delivered source, feedback lists that source ID as a correction
hint. The reviewer must still reassess the claim and submit the corrected ID;
the controller does not assign evidence or approve on its behalf. Source paths
are displayed alongside new read IDs, and the schema calls out required reasons
and citations. Ordinary formatting repair should reuse saved reads and checks.

## Reusable citations and review handoffs

Read tools return a ready-to-use `citation` object alongside the actual content:

```json
{"source": "read:...", "excerpt_id": "excerpt:..."}
```

The reviewer can copy this object into a claim's `citations` array without
reproducing HTML, Unicode punctuation or JSON escaping. The controller records
the delivered span and binds its reference to the candidate scope, source ID and
source digest. Unknown references, another candidate's references and changed
sources are rejected. A paged read cites only the delivered page; it cannot
stand in for unread content. Optional literal quotes still must match exactly,
including within the referenced span when both forms are supplied.

Reasons, all assigned criteria, regression assessment, verification coverage and
limitations remain required. A check reference is still check evidence, not
implementation evidence. Referencing real text does not prove that the reviewer's
interpretation is correct. Accepted receipts retain the actual cited content.

Unattended item handoffs preserve the evidence catalog for the same candidate.
The replacement reviewer can retrieve earlier source and check reads with
`read_review_evidence`; it supplies its own assessment. The previous reviewer's
decision is not inherited. Old saved catalogs without excerpt references gain
references when read, with no reset of checks, permissions or attempt history.
The item's decision-coaching phase keeps this saved-evidence reader available;
it no longer demands citation corrections while forcing a decision-only call.
Existing allowances and repeated-non-progress recovery still apply.

An explicit `list_files` directory now discovers readable generated files even
when Git ignores them, so a reviewer can find built HTML without guessing paths.
The root inventory still follows Git ignore rules; protected names, symlinks,
dependencies and workspace boundaries remain excluded. Finding an artifact does
not establish that it was produced by the current successful check; reviewers
must assess its provenance and request missing verification through existing
permissions.

Automatic catalog eligibility also rejects explicit moderation/classification
tasks and narrowly identified safety-classifier families despite generic gateway
chat/tool flags. This extends the non-chat filter; it does not blacklist a
provider or treat a general model's name containing `safe` or `guard` as proof
of incompatibility. Unknown general assistants retain the usual qualification
path. No new cumulative review cap is introduced.

## UI and independence

`inspect_image` now works in both checkpoint dispatchers and final review. It uses
the reviewer role, including its metered request, cancellation and identity checks.
Missing, simulated, or unavailable image analysis is not valid visual evidence.
SVG source is labeled code evidence, not a rendered screenshot. Image bytes receive
a digest; an inspected screenshot still needs to represent the feature being
reviewed.

Reviewer guidance calls for inspecting related styles, icons, handlers, callers,
imports, removed behavior, tests and assertions where relevant. Source inspection
is not a browser interaction test. The harness does not yet start a browser and
capture a fresh screenshot automatically for every project. Reviewers must report
that limitation when it matters, and request targeted verification under the
existing task's permissions when needed.

Provider-reported identity checks and existing authorized identity recovery still
apply. Different configured route names alone cannot prove different underlying
models. Manual model choices, including the existing local single-model policy,
are unchanged in this PR; stronger independence needs routing and product policy,
not a new stop at the end of a task. Older metadata is not fabricated.

## Measuring improvement honestly

Completing a review or emitting APPROVE no longer earns the reviewer the ranking
boost associated with successful task completion. Independently validated outcomes
can still inform ranking. Availability, compatibility, operator choices and model
metadata remain routing inputs; this is not a measured reviewer-accuracy score.

The deterministic regressions exercise invalid approval, retrieval and correction,
reviewer replacement, large packets, saved receipts, image dispatch and legacy
compatibility. They do **not** measure how often live models find real defects.
New tests are in-memory; existing Git/check workflows are reused.

Remaining work needs evaluation rather than claims based on a green suite:

1. An optional browser verification capability that captures the current task copy,
   exercises the requested UI behavior and nearby controls, and binds artifacts to
   the candidate. Preserve task permissions and avoid assuming one web framework.
2. A defect-detection evaluation set with known broken and correct variants: missing
   CSS, removed handlers, assertions weakened to pass, incorrect working directory,
   edge cases and clean changes. Score missed defects and invented defects as well
   as eventual completion, requests and cost. Live trials need explicit model and
   spending authorization; they are not routine CI.
3. An independently adjudicated outcome path before using user-reported regressions
   as training/ranking facts. Neither a complaint nor a human merge alone establishes
   reviewer correctness. Any future public statistic needs its signed evidence
   contract and sample limitations.
4. Consistent identity comparison based on available route/served metadata. Do not
   infer the real model behind arbitrary aliases or maintain a hardcoded model list.
5. Runner-reported discovery/execution/skip counts and test-assertion changes, when
   available. Preserve unknown counts instead of inferring them from exit zero;
   keep check execution within the existing command authority.
6. Review grouping around related behavior across files. Current chunks still use
   size boundaries; synthesis citations improve their evidence, but do not prove
   that every dependency or interaction has been inspected.

Evidence citations establish provenance. A reviewer can still misunderstand a real
excerpt or miss a dependency. The contract makes unsupported approvals detectable
and inspectable; behavioral and visual checks are still necessary where relevant.
