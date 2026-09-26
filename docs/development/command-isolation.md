# Optional command isolation

Host execution remains the default. A separate task copy by itself is not an OS
sandbox. The optional `bubblewrap` backend adds Linux namespaces and restricted
mounts to **both** authorized task commands and verification checks. It does not
grant command permission, relax check scope, or replace independent review.

## Selection and persistence

An operator can set `CHEAPOS_COMMAND_BACKEND=bubblewrap` before starting cheapoS
on Linux. This is a default for new tasks only. Alternatively, send
`"command_backend": "bubblewrap"` (or `"host"`) in the authenticated operator
request to `/api/tasks`, `/api/branch-runs/plan`, `/api/branch-runs/plan-start`, or
`/api/branch-runs/prepare`, alongside the normal required fields. There is no UI
selector in this initial backend release. Inspect `command_backend` in the task
or Session permissions API and `execution_environment` in command/check receipts.

Only those two values are accepted. A task captures its selection and retains it
across restart, Resume, model handoff, planning-to-execution, scheduled runs and
merged-PR follow-ups. Existing records without the field explicitly mean host;
changing the startup default does not reinterpret them. Models have no backend
selection tool or argument. There is no in-place downgrade endpoint: create a
new task to choose different execution authority.

Task command grants and unattended approval bind the selected backend. Isolated
checks support exact command consent and task command permission; host project
unittest-profile grants are not reusable in this different environment. Check
identities include the backend policy version, launcher digest, kernel and fixed
environment, alongside the existing candidate/command/runner/configuration
identity. Changed or unavailable backends cannot reuse passing evidence. Setup
commands still invalidate dependency evidence without becoming verification.

## Linux contract

The operator must provision a trusted, root-owned, non-setuid `/usr/bin/bwrap`
with `--disable-userns` support and a kernel permitting unprivileged user
namespaces. cheapoS does not install it, start a VM or daemon, or pull images.
macOS and Windows do not implement this backend. Missing binaries, namespace
restrictions, unsupported flags and launch failures never fall back to host.

The launch uses required user, PID, IPC, UTS, mount and network namespaces;
capabilities are dropped and further user namespaces disabled. It exposes:

- Read-only system runtime trees `/usr`, `/bin`, `/sbin`, `/lib`, `/lib64` where
  present, plus the loader cache/configuration files. These are trusted host
  toolchains, not a separately pinned container image.
- One writable task workspace at its existing absolute path. Git directories
  are read-only and external-worktree Git marker files are masked. Other task
  records, the source checkout, home directories, `/run` and host sockets are
  not mounted. Workspace hard links, sockets, devices and FIFOs are refused;
  unreadable entries fail closed. Symlinks resolve inside the namespace.
- Fresh `/tmp` and `/home/worker`, a namespace `/proc`, and a minimal `/dev`.
  Home/temp state is discarded at command exit; install persistent dependencies
  inside the task workspace. No host environment variables or credentials are
  inherited. PATH is `/usr/bin:/bin`; Python search paths stay in the workspace.

There is no network opt-out or port forwarding. Network-dependent dependency
installation and host preview launches are unavailable for isolated tasks.
Manual and agent browser previews reject the request before their separate host
launcher runs; isolated tasks cannot grant agent browser execution permission. Toolchains
outside the mounted system trees must be prepared within the task copy. Normal
component working-directory checks still reject escapes and Git internals.

The launcher starts a separate process session. Cancellation, timeout, output
limit and callback errors kill the process group; normal exit also cleans up
remaining group members. Bubblewrap's PID namespace/reaper and die-with-parent
policy contain descendants that start new sessions and terminate them when the
sandbox ends. The usual output spool and check time/output limits still apply.

## Limits and validation

This is defense in depth, not a zero-risk claim or support for arbitrary hostile
repositories. It shares the host kernel and system runtime. It does not add
seccomp syscall filtering, CPU/memory/disk quotas, or mediation of controller
file tools, Git operations, model traffic or URL tools. Commands can destroy
writable task files and exhaust host resources. Concurrent host processes must
not mutate task mounts while commands run; preflight checks are not protection
against a hostile same-user process racing filesystem changes. Source exclusion
is not a secret scanner, and command output can reach configured models.

Deterministic tests exercise policy construction, refusal, permission binding,
identity/reuse, persisted receipts, process-exit cleanup and provider request
assembly. They do **not** prove kernel enforcement. The implementation was
validated on macOS, where isolated execution must fail closed; live Linux
namespace behavior remains unverified in that environment. Before relying on a
Linux installation, qualify a disposable repository with an outside sentinel:
confirm the command cannot read/write the sentinel, write the runtime mounts,
connect to a host listener or public network, or retain a background descendant
after normal exit/cancellation/timeout. Also verify an ordinary offline test can
write task files and produce its retained check receipt. Do not use personal
credentials as a qualification fixture.

Backend behavior follows the upstream [Bubblewrap option contract](https://github.com/containers/bubblewrap/blob/main/bwrap.xml)
and [security notes](https://github.com/containers/bubblewrap#sandbox-security).
