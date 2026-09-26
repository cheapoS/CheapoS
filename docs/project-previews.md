# Project previews

Open a project's three-dot menu → Project settings → Preview settings.
Save a start command, optional setup command, working directory, local URL,
environment overrides, and manual test steps. Saving executes nothing.

In branch review, expand **Try it before merging**. Inspect or override the
configuration and click **Launch preview**. Launch uses the exact displayed
commit, cloned into a separate temporary directory without hard links.
Uncommitted edits require a new committed/reviewed revision first.

Commands are argument lists, not shell scripts. For example, use `npm ci` as
setup and `npm run dev -- --host 127.0.0.1 --port {port}` as start.
Choose an unused port and local HTTP URL. `{port}` expands to the URL port;
`{profile}` expands to a separate test-data directory. Configure your app to
actually use that directory and test services: a separate checkout is not a
security sandbox. Inherited credentials and production database URLs can still
reach real services. Environment settings are saved locally with owner-only
file permissions; prefer credential references over secrets.

For cheapoS, suggested settings are:

- Start: `python3 -B run.py --no-open --port 5174 --data-dir {profile}`
- URL: `http://127.0.0.1:5174`
- No setup command.

Only committed tracked files are copied. Ignored dependencies and local config
are not copied; use setup/environment settings where needed. The separate
cheapoS profile may need its own connection setup.

The panel shows the launched commit, status, latest 64 KB of output, and an
outdated notice if the task changes. **Open preview** opens the configured URL;
the process may still be initializing. **Stop preview** stops its process group,
including setup processes. App shutdown stops previews; restart does not relaunch
them. Temporary directories are retained for inspection; the path is shown in
the panel. You can remove them after stopping the preview.

Write manual steps as action → expected result, including nearby functionality:

1. Click the sample's three-dot button → confirmation appears.
2. Cancel → sample remains visible.
3. Confirm hide → sample disappears.
4. Send a chat message and open New chat → both still work.

These are operator checks, not claims of automated verification. Task acceptance
criteria are shown separately for reference. Testing is optional and never marks
independent review or automated checks as passed. Previewing does not merge,
push, or make model requests. Launch overrides last for that preview; **Save as
project defaults** reuses them for later tasks.


## Agent browser verification

Open **Session permissions → Configure agent browser verification** while the task
is paused. Inspect the start/setup commands, working directory, environment and
local URL, then click **Authorize browser verification**. The branch review preview
panel offers the same consent. Saving project defaults or launching a manual preview
does not grant agent browser permission. Changing consent requires pausing; revocation
is available while running and stops the owned browser and preview.

Install the optional browser runtime in the same Python environment that runs cheapoS:

```sh
python3 -m pip install "playwright>=1.48,<2"
python3 -m playwright install chromium --only-shell
```

No dependency installation happens from a browser tool. Missing runtime errors remain
explicit limitations. These local browser actions make no inference requests;
`inspect_image` uses the selected role's existing metered model and spending authority.

After consent, a worker can use `browser_preview`:

1. `start` freezes the current task's eligible files, including uncommitted edits,
   into a separate preview copy. It never commits or changes the task workspace.
2. `status` reports startup/setup state and bounded logs. `open` starts a fresh
   headless Chromium context and navigates to the configured URL when the app is ready.
   If startup is still pending, inspect status before opening again.
3. `observe` returns rendered body text, visible control descriptors/selectors,
   viewport, URL, console messages, page errors and failed HTTP requests.
4. `navigate`, `click`, `fill`, `select`, `press` and `viewport` exercise the local
   preview. Navigation and browser HTTP/WebSocket requests stay on the displayed
   origin. Keys, selector/input lengths, viewport size and operation time are bounded.
   There is no arbitrary JavaScript, file upload, browser profile or external-site tool.
5. `screenshot` retains a viewport PNG and returns an evidence ID plus a `browser:`
   image reference. `stop` ends the owned processes. Task pause, worker exit and
   graceful app shutdown also stop them. Restart preserves consent and evidence,
   but never restores a live browser or silently relaunches commands.

The preview uses a fresh browser context, separate profile directory and a reduced
process environment. Use `{profile}` for app test data and disposable test services.
Commands and application code still run as the local user: this is not an OS sandbox.
The preview port must be unused. Setup must leave the frozen eligible source files
unchanged; ignored build/dependency output can be generated normally. Excluded files,
source mutations or missing dependencies must be resolved rather than treated as a
successful verification. Browser readiness does not establish application correctness.

`read_browser_evidence` lists the latest 100 retained observations; an exact ID reads
older records. Records include candidate, originating item, session, operation,
configuration digest and captured result. Source bytes/modes, workspace generation,
plan or operator directions changing invalidate current reads. Changing the authorized
preview configuration also invalidates old reads. Revocation removes execution
permission but preserves evidence. Screenshot bytes are verified against their saved
SHA-256 digest, including after restart. Evidence lives outside the task workspace.

Independent item and final reviewers receive the evidence reader and `inspect_image`,
not browser execution tools. They can list retained records, read a current screenshot
reference, and inspect it using their own model. Console/text records are supporting
observations; they do not replace source/visual citations, exact required check receipts,
or a separate explicit independent decision. A failed operation remains a diagnostic,
and a screenshot alone is never an approval or passing automated check.
