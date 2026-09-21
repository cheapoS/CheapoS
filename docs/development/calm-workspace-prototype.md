# Calm workspace prototype

This is a local UI experiment, not a replacement for the execution or review
system. It borrows the compact workspace hierarchy of tools such as ZCode while
keeping cheapoS's own controls and visual identity.

## Direction

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

The experiment is scoped by the `calm-workspace` body class. Its shared tokens
live together at the end of `dist/styles.css` so this direction can be evaluated
and revised before integrating it into the existing styles.

Use a 14px reading size, 12px supporting text and 11px metadata. Keep conversation
width at most 900px. Use dark neutral surfaces, muted mint for actions and
success, and the existing warning/error colors for attention. Prefer a subtle
line or spacing to another enclosing panel. Keep keyboard focus and native
disclosures usable; respect reduced motion.

## Local preview

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
The completed fixture does not exercise a live provider stream or an actual
GitHub pull request; those still need a later real-task trial before shipping.

## Validation

Run `python3 -B scripts/check.py --plan`, then the selected frontend checks.
The new summary cases are in-memory Node tests: latest check versus historical
failures, stale approval during active work, and a conversation with no edits.
No Python workflow tests or live-provider tests are added by this prototype.
