# Settings that make their scope obvious

Status: proposed design, 2026-09-17. No application behavior is implemented by
this document. Implementation entry point: [T91](../tasks/T91-settings-system.md).
The [clickable screen study](settings-preview.html) uses fictional local state;
it cannot change cheapoS settings or dispatch model requests.

## The product decision

**A chat keeps its saved setup. One Save changes one named scope.**

There are three places to configure work: **This chat**, **Project defaults**,
and **New chat defaults**. Shared connections and browser appearance are separate
resources with their own clearly labeled settings. The same controls and visual
language can be reused across scopes; the destination must never be inferred
from whichever chat happens to be selected in the background.

Success means an operator can change a reviewer for chat A, continue its saved
review, and know that chat B and future chats are unaffected. A model or provider
failure should still be recovered automatically within the saved authority, per
[AUTONOMOUS_WORKFLOW.md](../../AUTONOMOUS_WORKFLOW.md). Settings are for choices,
not a prerequisite for repeatedly rescuing routine failures.

## What is broken today

Verified against the source at `98401b1`:

- `executionPreferences()` in [app.js](../../dist/app.js) combines global
  execution preferences, project role mappings, and current-chat limits in one
  form. Its submit handler writes `/preferences`, sometimes `/tasks/:id/limits`,
  then `/role-mappings`. The task-limit failure is caught without being shown.
- Its footer says defaults apply to new chats even when the form changes a
  project's roles or attempts to update the current chat. `User-selected` and
  `Default` do not explain where a value came from.
- [role_mappings.py](../../cheapos/role_mappings.py) stores app and project
  defaults, while [routing.py](../../cheapos/routing.py) captures task execution
  and provider choices. These are different scopes exposed as one setup.
- The current standalone `chatLimits()` is closer to the right pattern: it
  explicitly chooses a task or new-chat defaults and does not silently resume.
- The recent [branch controller](../../cheapos/branch_controller.py) fix keeps
  an authorized run's saved model policy when app defaults change. Preserve that
  property throughout this work; do not reconstruct authority from defaults.

## Entry points and navigation

| Entry point | Opens | Destination of a save |
| --- | --- | --- |
| Composer **Chat setup**; model/limit links in session details | This chat, identified by title and project | This task ID only |
| Composer **Chat setup** before first submission | This new chat | Draft only, then captured on creation |
| Project menu **Project settings** | Project defaults for the named project | New chats in that project |
| Bottom-left **Settings → New chat defaults** | Installation defaults | Future chats unless overridden by their project |
| **Settings → Connections**; connection problem link | Shared connections | Named connection used by potentially many chats |
| **Settings → Appearance** | This browser | Existing layout/display preferences only |
| **Settings → Usage & sharing** | This installation | Usage inspection and existing explicit leaderboard opt-in |

Use a wide settings surface, not a stack of small dialogs. Desktop target:
approximately 960–1120px maximum width with a 200px navigation column and a
readable form area. Use the app's existing mint accent, dark/light appearance,
native controls and typography. On small screens, navigation stacks above the
form. Use one content scroll area and a visible action footer. Keep focus inside
a modal and restore it to its opener; a full-page implementation is also valid.

The navigation can contain contextual entries **This chat** and **Project
defaults · cheapoS**, followed by **New chat defaults**, **Connections**,
**Appearance**, and **Usage & sharing**. Hide unavailable contextual entries.
Opening from a chat always starts at This chat. Opening from the app Settings
button starts at its last app section, never silently at a selected chat.

Each scope has a named header, not a generic Settings title:

```
THIS CHAT                         PROJECT DEFAULTS
Fix project manager              cheapoS
Changes affect only this chat.   Used by new chats in this project.

NEW CHAT DEFAULTS                 SHARED CONNECTIONS
Starting setup                    OmniRoute & local models
Used unless a project overrides.  Changes can affect chats using this connection.
```

Use three work-setting sections: **Agents**, **Spending & work**, **Permissions**.
Sections share one draft and one scoped Save; switching sections does not save.
Switching scope with unsaved edits asks **Save [scope] / Discard / Keep editing**.
Do not hide important controls behind the technical logs.

## Ownership, inheritance, and capture

| Setting | Owner | Meaning for an existing chat |
| --- | --- | --- |
| Interactive / Unattended work mode | New-chat draft, then task | Saved workflow; conversion uses a dedicated workflow transition |
| Where agents run; planner/worker/reviewer choices | App defaults → project overrides → draft overrides | Fully resolved and captured; task changes use a task operation |
| Optional local coordinator and installed model | Same default hierarchy | Captured on/off and model; checked only when assistance is needed |
| Spending policy and work allowance | Same default hierarchy | Task authority; cumulative usage is retained when edited |
| Command grants, accepted plan, verification requirements, merge approval | Existing task/project authorization systems | No generic settings save creates or widens these grants |
| Connection address, credentials, adapter, enabled state and access declarations | Shared connection registry | Availability/revocation remain current; changing identity does not silently rebind saved chats |
| Which existing connections a task may use | Default hierarchy, constrained by connection policy | Captured authorized connection IDs and policy revisions |
| Sidebar width, wrapping, display preferences | This browser | Presentation only; no execution or billing authority |
| Lifetime usage and leaderboard sharing | This installation | Existing opt-in workflow; never implied by model setup |

Default resolution for a **new** chat is app values → project overrides → draft
overrides, field by field. A project stores only overrides. **Use new chat
default** removes an override; it must not copy today's parent value permanently.
**Automatic** is an explicit role choice, not an empty value meaning inherit.
False, zero dollars, and an empty allowed-connection list are explicit values.
An empty allowed list means no remote routes, never all routes.

Before first submission the draft displays effective values and their sources.
If defaults change while a draft is open, preserve typed overrides and show a
small **Defaults changed — review setup** notice. Do not silently replace the
values being authorized. First submission sends the displayed revision IDs;
stale setup returns a precise refresh decision without starting paid work.

At creation, persist a complete resolved setup and per-field provenance in the
task. An unattended planning task captures its setup before planner requests;
plan approval then binds the reviewed proposal and setup revision. Changing a
draft setting after planning must update the proposal through its existing
revision/approval flow, not leave an approval button attached to stale authority.

After capture, defaults are **not live inheritance**. Use these source labels:

- Project form: **New chat default**, or **Project override**.
- New-chat draft: **From project defaults**, **From new chat defaults**, or
  **For this new chat**.
- Existing task: **Saved for this chat**; optional Details says **Copied from
  cheapoS project defaults on creation**. Later edits say **Changed in this chat**.
- Legacy task without reliable provenance: **Saved for this chat · source unknown**.

Do not infer provenance from coincidentally equal model names. Reset in an
existing chat means **Review current defaults**, showing a before/after draft
for this chat. It never reconnects that chat to live defaults. Copying a setup
to defaults is a separate, explicit action opening the destination for review.

## Agents: useful choices without routing jargon

**Where agents run** has three approachable choices:

- **Remote through OmniRoute** — remote work using authorized connections.
- **Local** — installed local models for work.
- **Local chat + remote work** — local conversational handoff, remote heavy work.

Keep placement separate from role selection and optional recovery assistance.
The existing `manual` execution value combines both concepts; migrate it by
preserving its actual provider bindings. For mixed legacy placement, show
**Custom saved setup** and its role rows rather than forcing a new preset.

Show planner, worker and reviewer as labeled rows. Each row has a searchable
model choice with these policies:

| Choice | Behavior |
| --- | --- |
| Automatic | Engine selects and changes eligible models within saved access, independence and spending policy |
| Prefer a model | Try that model when eligible; permit authorized alternatives after failure or cooldown |
| Use only this model | Remain pinned; show that an unavailable model may require waiting |

**Prefer a model is proposed behavior**, not a claim about current code. Ship it
only when the runtime honors it in planning, Interactive work, item review and
final review. The first release can offer Automatic and Use only this model.
Never reinterpret an existing explicit/pinned model as a preference on migration.
Automatic recovery remains enabled within the chosen policy; no new retry-count
controls or “enable error recovery” switch are needed.

Existing tasks show two different facts: **Selection: Automatic** and
**Currently using: [role model] via [connection]**. A failed attempt is historical,
not the configured selection. Availability badges include a time or “not checked”;
a cached catalog entry is not a promise that inference will work.

Preserve existing independence rules. The explicit role-mapping validator
currently rejects worker = reviewer and worker = planner. Other execution paths
have legacy local fallback behavior; do not silently relabel that as independent
review. Use the current runtime's validated capability result and surface a
precise conflict when a new selection is invalid. Changing independence policy
is outside this task. A valid review finding survives every model handoff.

The **Local coordinator** sits below the role rows:

```
Local help when needed                              [ On ]
Model                                               gemma4:31b
Consulted when an eligible stall needs help. Idle otherwise.
```

Recommend it when a suitable installed model is available, but retain explicit
opt-in and existing saved choices. Opening or saving settings must not start
inference, pull models, keep a model thinking, or probe every route. A manual
**Refresh installed models** fetches metadata. If help is unavailable, ordinary
authorized recovery continues. Don't promise coverage of every failure phase
until the implementation actually supports it.

## Spending & work: two different controls

Place **Spending** first:

- **Free only** keeps the current free/included-access policy and charge guard.
  Explain briefly that estimates are not provider receipts; detailed billing
  uncertainty belongs in accounting details, not every summary label.
- **Allow paid models** requires an explicit finite currency cap and selection
  of eligible connections/models. Merely choosing a paid model must not enable it.
- Existing task: show **Accounted so far / Total chat cap**. A $1 cap means total
  cumulative authority of $1, not $1 more after each Save or Resume.

Then **Work allowance**: **Bounded** with the current values, or **Uncapped work**.
Do not invent new default thresholds in this redesign. Explain uncapped once:
**No cumulative work caps. Spending limits, permissions, and review still apply.**
Advanced details may expose supported per-request output or command timeout
limits, clearly distinct from cumulative allowances. Measurement mode remains
its own trial feature, not a synonym for unlimited spending.

`development_mode`, takeover authority, `uncapped_work`, and measurement currently
have different implications. Do not make a single switch set all four flags.
Show the ordinary Work allowance control plus an Advanced readout of any saved
development/takeover authority. Retire duplicate controls only after an explicit
mapping of their current semantics and authorization has been tested.

No split reported/reserved token string on the compact composer, role rows, or
collapsed accounting heading. Show the accounted total; the accounting dropdown
retains reported usage, reservations and uncertain requests. This is presentation,
not permission to discard reservations or count them as measured free usage.

## Permissions and shared resources

Permissions is primarily an inspection surface: show this chat's command grants,
any applicable project grants, and links to their existing specific approval or
revocation flows. No “trust everything” checkbox; an execution default is not a
command grant. Accepted plan edits, new verification commands, and merge approval
stay in their dedicated review flows. A model-selection save cannot modify them.

Connections lists OmniRoute connections and local Ollama with status, endpoint,
enabled state and a **Used by N saved chats** link. Keep provider credentials in
the existing credential store. Never copy secrets into settings snapshots,
source-controlled project files, exports, browser storage, or task history.
Remote inference continues through the authorized gateway; this redesign adds
no direct-provider path.

Connection configuration owns credentials/access declarations, not agent-role
choices. Editing an address or access policy shows the affected connection and
chats before applying. Preserve current active-task guards. Never implicitly
stop all chats or swap their connection identities. Revocation/disable must stop
future dispatch even for captured tasks; a saved setup is not permanent access.
Credential rotation for the same verified identity follows current connection
policy; do not invent a global-default revision that invalidates every chat.

Appearance explicitly says **This browser**. Usage & sharing explicitly says
**This cheapoS installation** and reuses the existing leaderboard pairing and
consent flow. These sections organize existing functionality; this task does not
introduce a hosted account, new telemetry, sync service, or new theme controls.

## Save and continuation behavior

Primary actions name their destination:

| Screen/state | Primary action | Confirmation |
| --- | --- | --- |
| New chat defaults | Save new chat defaults | Saved for future chats |
| Project defaults | Save project defaults | Saved for new chats in cheapoS |
| New-chat draft | Use for this new chat | Draft setup updated |
| Existing idle chat | Apply to this chat | Chat setup updated |
| Paused chat, valid continuation | Apply & continue | Setup saved. Continuing review… (actual phase) |
| Paused chat, operator wants to stay paused | Secondary Apply without continuing | Setup saved. Chat remains paused |
| Active chat, settings change needs a boundary | Pause, apply & continue | Waiting for the current operation; then applying setup |

The active-chat action is an explicit request, not an implicit consequence of
opening settings. Persist it, let the current operation reach its safe boundary,
validate and apply once, then continue the remaining operation. No extra Resume
click. It must not discard in-flight tool results or reset task progress. If the
existing executor cannot support this safely yet, advertise that capability as
unavailable and keep the edit draft with **Pause to apply**; ship the combined
operation before claiming active edits are seamless. Do not queue edits silently.

The form's footer presents a compact changed-fields summary when authority
changes, e.g. **This chat: reviewer Automatic → model X only; spending unchanged**.
The explicit scoped action is the authorization for those changes. Avoid an
additional confirmation for every ordinary save. Genuine expanded spending,
connection access or command authority still uses its specific review step.

Changing a reviewer while paused at final review must continue final review.
Preserve edits, worker identities, valid checks, findings, usage and failed-attempt
history. Revalidate affected review evidence under the new reviewer policy; never
silently preserve an approval that relied on an incompatible policy. Switching
work mode or placement after work starts is not a generic settings patch: use a
dedicated supported transition or explain why it is unavailable without discarding
the draft. Do not treat it as a new task by accident.

Save returns after durable acknowledgement, before probes, Git scans or model
selection. Disable duplicate submission immediately; show Saving while awaiting
the response and only say Saved after it is durable. Target local acknowledgement
under 500ms in a deterministic fixture; measure it, not with a flaky hard deadline.
Long operations return an operation ID with persisted stages, visible progress,
and cancellation where supported. Closing the form does not cancel saved work.

Failure stays inline with the unsaved fields intact. No swallowed error and no
generic success toast after a partial save. If continuation fails after a valid
save, say **Setup saved; waiting for [actual prerequisite]** and retain the operation
for ordinary recovery. Saving and running are separate outcomes.

## Implementation contract

This is a boundary contract, not an instruction to build a second execution
engine. Reuse current validators, locks, connection registry, task operations,
authorization receipts and continuation executors.

### One authoritative settings store

Introduce a small `settings_store.py` for execution **defaults** and project
overrides, with one versioned local document, atomic replacement under the engine
lock, and revision checks. Keep connection secrets, permission grants, usage and
task snapshots with their existing owners. Example logical shape (field names
may adapt to existing validators):

```json
{
  "schema_version": 1,
  "generation": 12,
  "defaults": {
    "revision": 5,
    "values": {
      "placement": "remote",
      "roles": {
        "planner": {"strategy": "automatic"},
        "worker": {"strategy": "automatic"},
        "reviewer": {"strategy": "automatic"}
      },
      "coordinator": {"enabled": false, "model": ""},
      "limits": {"dollars": 0, "uncapped_work": false}
    }
  },
  "projects": {
    "<existing canonical project key>": {
      "revision": 2,
      "overrides": {"roles.reviewer": {
        "strategy": "only", "connection_id": "gateway-1", "model": "example/model"
      }}
    }
  }
}
```

This is a partial illustrative record, not a complete input fixture. Fill all
required limits through existing validation. Role references bind connection ID
and model ID, not a display label. The resolver uses a fixed field allowlist;
dotted override keys are not arbitrary task-object paths. A project key uses the
existing registry's canonical identity (currently repository path); do not add a
second project-ID system as part of this work.

The document generation supports atomic persistence; scope revisions determine
edit conflicts. A write to project A must not make project B's unchanged scope
revision stale. A defaults change does change the parent revision for both
projects, so inherited values are reviewed when their next draft is saved.

A task gets `settings_snapshot` with resolved values, source scopes/revisions and
a task settings revision. Existing task/run fields and authorization receipts
remain authoritative during migration; introduce a single adapter rather than
two competing runtime readers. Every task mutation updates its snapshot and
existing execution/authorization representation together through the owning
operation. Contradictory records block dispatch with a specific internal cause,
not a silent global-default fallback.

### Proposed API surface

| Operation | Contract |
| --- | --- |
| `GET /api/settings/defaults` | Values, revision, schema and capabilities |
| `GET /api/projects/settings?project=…` | Overrides, resolved values, per-field sources, own/parent revision |
| `GET /api/tasks/:id/settings` | Saved/effective setup, current role models, grants summary, editable fields, transition capabilities and revision |
| `POST /api/settings/defaults` | One validated patch to app defaults only |
| `POST /api/projects/settings` | Explicit project key; set/remove allowlisted overrides only |
| `POST /api/tasks/:id/settings` | Explicit task revision and changed fields; intent apply / apply-and-continue / pause-apply-and-continue |

Every mutation is authenticated with the existing same-origin/trusted-token
mechanism. Reject unknown keys, mismatched project/task ownership and unsupported
changes. Include `expected_revision` and a client operation ID. Exact retries
return the original result; reusing an ID with a different payload is an error.
Revision conflicts return the current values and field differences so the UI can
keep the draft and offer **Review newer settings**, not overwrite unseen changes.
Project saves validate against the parent revision as well as the project revision.

The task endpoint is an adapter to existing task limits, coordinator and operator
revision operations. It must not accept arbitrary `model_policy`, authorization
digests or task JSON from the browser. Validate the complete proposed change
before any mutation; persist the task, changed authorization receipt and operation
record in one crash-consistent transition using existing storage. A frontend chain
of independent POSTs is not a transaction. If more than one persistent file is
required, use a recoverable journal; prefer the existing single task record.

Returned fields distinguish `saved`, `pending`, `applied`, and `continuing`.
Capability responses explain fields that cannot be edited at this stage. Connection
health can refresh without changing the settings revision or accepted model policy.
No inference is triggered by GET, metadata refresh, or saving future defaults.

### Migration without surprises

1. Read existing `preferences.json`, `role-mappings.json` and public model config;
   normalize through existing validators. Preserve explicit false/zero values,
   local model selections, all connection bindings, pins and dollar limits.
2. Convert app settings and project role overrides into the new defaults document
   once. Record migration version and retain a recoverable local backup without
   copying secrets. Invalid legacy fields produce field-specific repair notices;
   never reset a paid/free policy to a more permissive fallback.
3. Existing tasks derive their view from saved execution/provider/limits/run
   authorization. Never refresh them from newly migrated defaults. Uncertain
   provenance remains unknown. Legacy missing fields use an explicit historical
   compatibility rule, not whatever defaults happen to exist today.
4. Redirect existing preference/config/role-mapping APIs to the authoritative
   store or clearly deprecate them. No ongoing dual writes to independently read
   stores. First-run setup, task creation, planning and all settings entry points
   must share the resolver; audit each caller before switching readers.
5. Saved views work offline and across restart. Keychain/authentication repair may
   be needed independently; never ask users to re-enter a remembered model simply
   because the gateway catalog cannot currently be fetched.

## Acceptance scenarios

| Scenario | Required result |
| --- | --- |
| Two chats, same project; change reviewer in A | A changes through authorized transition; B, project and app defaults byte-for-byte unchanged |
| Change app defaults while B awaits final review | B resumes with its saved policy; no false “run scope changed” failure |
| Change project defaults | Only later new chats use them; existing proposals/tasks keep captured values |
| Explicit project Automatic overrides a pinned app role | New project chats use Automatic; removing override restores app pin |
| App save makes an inherited project combination invalid | Reject with affected project/roles; no partial write or silent replacement |
| Another browser saves first | Revision conflict keeps the losing draft and explains changed fields |
| Switch selected chat while settings are open | Save targets the original named task or requests reopening; never the newly selected chat |
| Failure/restart during save; repeated click | No partial multi-scope change; at most one operation; truthful saved/pending state |
| Paused at final review, choose valid new reviewer | Apply & continue reviews remaining evidence, retaining findings and matching checks; no worker restart |
| Lower cap below accounted usage, or turn bounded on after its allowance | Show current usage and explain that applying leaves work paused; no allowance reset |
| Uncapped work, free-only task | No cumulative work ceiling; no new paid route or command permission |
| Connection disabled or rebound | Next dispatch respects revocation/identity checks despite saved setup |
| Open/save settings with offline providers | No inference/probe burst; saved choices still displayed |
| Coordinator enabled, ordinary work progressing | No continuous local inference; consultation only at an eligible need |
| Old manual/local setup migrated | Exact bindings preserved, mixed/unknown scope explained, no unsolicited automatic fallback |

Keyboard access, proper labels, focus restoration, contrast, visible error text
and layout at 320px, laptop and large desktop widths are required. Status/provenance
must not depend on color. The screen study demonstrates scope and save labels;
it does not simulate the real authorization, model-selection or resume engine.

## Delivery boundary

Implement [T91](../tasks/T91-settings-system.md) in its ordered slices. The first
useful outcome is unambiguous scope and no cross-chat writes. Do not bundle a new
router, project manager, permission model, telemetry system or general UI rewrite.
Preferred-model fallback and active pause/apply/continue require their own runtime
acceptance before being exposed. Keep existing automatic continuation behavior.
