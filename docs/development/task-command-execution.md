# Task command execution

Approve an unattended plan with **Allow task commands** selected to let its worker
prepare dependencies, diagnose errors, and run project commands without approving
every argument variation. This choice is visible on Review & Start and recommended
for unattended work. Uncheck it to retain exact-command/profile permissions.
Older tasks and API clients that omit `allow_task_commands` receive no new authority.

For an existing or Interactive task, pause it and open **Session permissions →
Allow task commands**, then Resume. The grant belongs to that task copy, survives
app restarts, and can be revoked from the same dialog while paused. Other chats and
projects do not inherit it. Repeated Start requests cannot expand an existing grant.
Full-suite verification still requires its separate approval.

The worker gets `run_command(command, directory=".")`. It executes one argument
vector in an existing task-relative directory, with streamed output and Pause
cancellation. Shell operators are not interpreted; use separate calls for separate
commands. There are no npm/Python/Cloudflare installation recipes: the worker uses
project manifests, documentation, files and actual process output. Ignored dependency
directories are not included in repository snapshots and may need local setup.
A missing runner discovered during planning remains visible in the proposal; a
valid task command grant allows the worker to prepare it before verification.

In default host mode, commands and dependency scripts execute as the local OS user. A private task copy
is **not a security sandbox**. The runner limits inherited environment variables,
uses a separate HOME, and validates working-directory containment, but arbitrary
programs can access host resources. This permission covers task-local work, not
deployment, publishing, credential access, Git mutations, or edits to other checkouts.
Those host-mode boundaries are instructions and authorization, not a claim of OS isolation.
New Linux tasks can explicitly select the [offline Bubblewrap backend](command-isolation.md),
which applies the same command permission inside restricted OS mounts and namespaces.
It never falls back to host; see that guide for setup, unsupported previews and limitations.

Command results are recorded separately from test evidence. Every general command
invalidates prior verification identity, including when only ignored dependencies
changed or execution failed. Commands do not satisfy required checks or approve
work. `run_checks`, candidate-bound check evidence and independent review remain
required. Existing spending/work budgets, cancellation, adaptive command deadlines,
and retained-output limits apply. Timeout/failure output returns to the worker for
another approach rather than automatically becoming an operator setup task.

API: `POST /api/tasks/<id>/branch-start` accepts the additional boolean
`allow_task_commands`. `POST /api/tasks/<id>/task-commands` accepts exactly
`enabled` (boolean) and `directory` (the displayed current task workspace).
Both use the normal trusted local request checks. `GET .../permissions` reports
`task_commands`; `expires: server_restart` describes only the older session grants.
