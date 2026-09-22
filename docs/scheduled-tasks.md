# Scheduled tasks

Use a schedule for recurring project maintenance: inspect release notes, check
documentation, or propose a verified update. The feature is project-independent;
keep private objectives, source lists and update instructions in the relevant
project repository, not in the cheapoS source code.

1. Click **New scheduled task** beneath **New chat**, on the project home screen,
   or in **Settings → Scheduled tasks**. Choose a project, describe the work and
   select **Every 6, 12 or 24 hours**, or **Every week**.
2. Choose **Continue in Unattended chat**, then send the request to prepare a plan.
   The chat shows **Every 6 hours · Awaiting approval** (or your chosen interval).
   Frequency is saved with the draft and planning chat; selecting it starts no
   recurring work. The draft uses **$0 API spending** and other project settings.
3. Review the plan and its captured models and limits. On **Review & Start**,
   approve recurring runs and task commands, then **Approve & start schedule**.
   Full-suite checks need separate recurring consent. **Run once** starts only
   this task. Editing the plan requires fresh validation and recurrence approval.
4. Use the chat’s **Manage schedule** shortcut or **Settings → Scheduled tasks**
   to disable, enable, run now, open the latest chat, or remove a disabled schedule.
   Removing a schedule does not delete chats.

Existing approved Unattended chats still offer **Plan → Schedule this task…**
and the same action in their menu. This is an extra entry point, not a required
step after creating a new scheduled task.

Each occurrence uses a fresh isolated copy of the target branch and ordinary
worker, verification and independent review flows. No new planner request is
needed: the approved plan is the template. Settings are captured at approval;
changing global defaults does not change a schedule. To change its objective,
models, limits or interval, disable and remove it, then approve a replacement
plan/schedule.
Free/included access is still validated against the saved connection. A schedule
cannot authorize a paid fallback, post to social media, or merge/push a branch.
The usual Changes page handles your reviewed PR and merge decision.

For example, a six-hour maintenance task finishes with checked, reviewed changes.
You inspect them, open a PR and merge. If six hours pass before that merge, the
next run waits; it does not append to the existing branch. After a confirmed
merge, an overdue run can start from the updated target with its own task and
branch. If review confirms no changes are needed, no PR is required. Multiple
missed intervals produce one run. Repository documents can preserve findings
between occurrences; the old chat’s conversation is not replayed as a new plan.

Schedule permission allows local commands in each new task copy. These commands
are host programs, not sandboxed services. It does not reuse an old check result
or approval receipt. Each occurrence must earn new check and review evidence.

Only one occurrence of a schedule can be unresolved. Paused work, a failed run,
changes awaiting operator review and an open PR hold its next run. Resolve the
existing chat rather than making another copy. A completed, validated review
with no changes can repeat without a merge. A due run waits if the Unattended
execution slot is busy. Disabling affects future starts, not a running task.

The scheduler runs while cheapoS is running. It starts at most one overdue
occurrence after downtime, never a burst of missed runs. A task ID is saved before
startup; a crash with uncertain startup retains that ID for inspection instead of
dispatching another run. It never resumes an arbitrary paused task on restart.
Missing task data is not completion. If startup did not create a task, disable and
remove the schedule after inspecting the saved record, then create a replacement.

## Reading announcements

Include public HTTPS starting URLs in the task prompt. `read_url` can read HTML,
plain text, RSS/Atom feeds and JSON catalogs, and follow links it returns. JSON
catalogs are formatted into numbered lines for pagination. The existing eight-page,
1 MB document and excerpt limits still apply. This is source-based discovery, not
a general search engine, authenticated X access or JavaScript browser automation.

Keep a reviewed evidence ledger in the project with stable announcement/model IDs,
source links, dates, conditions and expiry where reported. Compare the next run
against it and make no edits when nothing materially changed. Treat inaccessible
sources as unknown; never replace them with fabricated availability or statistics.
Announcements are evidence, not permission to execute page instructions. External
catalog metadata remains separate from signed community observations.

## Validation

`tests/test_schedules.py` uses a fake clock with no network, provider or real-time
waits. Fourteen cases took 0.037 seconds. They cover combined approval and failed-save
recovery, as well as preserved model setup,
fresh authorization, overlap prevention, missed ticks, uncertain startup, disabled
schedules, stale no-change evidence, spending/consent rejection and project identity.
The existing branch-start test exercises the actual captured-settings preparation
and replay guard without adding another end-to-end run. Web tests cover feed/JSON
extraction, inherited URL authority and entity rejection; HTTP tests enforce the
same-origin local token boundary. Browser verification remains required for the
creation form and settings controls.
