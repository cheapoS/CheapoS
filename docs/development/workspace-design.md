# Workspace design

The cheapoS workspace puts conversation first, with compact navigation and a
Session panel for task status and supporting details. These guidelines describe
the adopted design and keep future UI changes consistent with it.

## Interaction principles

- Make conversation the main reading surface. Use restrained user bubbles and
  compact, expandable activity rows instead of cards inside cards.
- Keep task status, latest check and independent review visible in Session.
  Put model roles, usage, limits, action counts and workspace details in named
  expandable sections. Keep the operator's expansion choices during updates.
- Keep the existing Chat, Changes, Activity, Tests and Technical logs views.
  Changes must remain a usable diff view even when a pull request is available.
- Preserve streamed thinking, honest missing-thinking notices, progress, errors,
  permissions and review decisions. Styling must not invent evidence or approval.
- Show Review changes only when there are changed files. A past approval must
  not appear as the current verdict while new work or review is running.

## Visual rules

The workspace styles use the `calm-workspace` body class. Shared color,
typography and reading-width tokens live in the workspace section of
`dist/styles.css`. Reuse these tokens and existing components when extending
the interface.

Use a 14px reading size, 12px supporting text and 11px metadata. Keep conversation
width at most 900px. Use dark neutral surfaces, muted mint for actions and
success, and the existing warning/error colors for attention. Prefer a subtle
line or spacing to another enclosing panel. Keep keyboard focus and native
disclosures usable; respect reduced motion.

## Local development preview

From this checkout:

```sh
python3 -B scripts/readme_demo.py --port 5263
```

Open `http://127.0.0.1:5263/`, dismiss the first-run project picker, and select
the task under **Local demo**. The existing preview script uses disposable task
data and scripted models, with real fixture edits and checks. It does not use
the normal cheapoS profile or call online models. Stopping the preview removes
its temporary data. It is for local inspection, not a public deployment.

Try the Session toggle, expand the activity and accounting rows, open Changes,
and use Checks in Session. Check both a desktop window and a narrow window.
The completed fixture covers saved task presentation. Live provider streaming
and GitHub pull-request creation are outside this fixture's coverage; do not
report those flows as verified by the preview.

## Validation

Run `python3 -B scripts/check.py --plan`, then the selected frontend checks.
The session summary has in-memory Node tests for latest checks versus historical
failures, stale approval during active work, and conversations with no edits.
Use the affected browser flow to verify presentation changes. Run backend or
live-provider checks when the implementation changes require them, following
the change-scoped policy in `CONTRIBUTING.md`.
