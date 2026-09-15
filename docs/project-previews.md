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
