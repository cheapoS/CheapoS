# T93 — Show a total action count for this session

Status: **Planned — next UI task**, recorded September 17, 2026.
Implement after the current merge-conflict work is finished.

## Product outcome

Give the operator one readable measure of how much work cheapoS has done in the
current chat, with the existing breakdown immediately below it:

```text
This session · 899 actions

Worker calls          …
Tool actions          …
Reviewer calls        …
Planner calls         …
Coordinator calls     …

Checkpoints           …
Latest check          Passed
```

899 is illustrative. Use the actual session total and normal number formatting.
The headline should update with the breakdown during work in both Interactive
and Unattended mode. This is a per-chat total, distinct from
[lifetime usage](T81-lifetime-usage-savings.md).

## Counting contract

- Count each dispatched model request and each executed tool action once,
  across all roles. Include retries, recovery, and connection probes that
  actually dispatch; an unsuccessful attempt is still work performed.
- Do not count queued requests that never dispatch, UI clicks, polling,
  rendering, or repeated saves of the same event.
- Use non-overlapping categories that add up to the headline. Inspect existing
  counter semantics first: controller worker turns, reviewer iterations, model
  requests, and tool actions are not interchangeable. Do not simply sum all
  current sidebar values and label that sum unique actions.
- Checkpoints and verification outcomes remain useful breakdown information,
  but must not add another action when their execution is already counted as
  a tool action. Explain this briefly in Details.
- Include the whole chat history across items, resumes, takeovers, model
  changes, and app restarts. Resetting a recovery allowance must not reset the
  session total. New chats start at zero.
- Use existing durable accounting where possible. If retention has removed
  historical evidence, do not fabricate an exact lifetime-of-chat count from
  the remaining rows. Show the known total with a compact coverage indication
  and explain its starting point in Details. Keep new totals durable without
  retaining unbounded raw logs.

## Implementation starting points

`dist/app.js` renders the session journey. `cheapos/metrics.py` aggregates role
requests and marks incomplete request history. Verify their current behavior
before changing the display. Prefer a small extension to those existing paths.

This task changes accounting presentation and any persistence necessary for an
accurate total. It does not introduce work caps or change spending, routing,
permissions, or autonomous continuation policy.

## Acceptance and validation

- The headline is visible directly above its breakdown in both work modes,
  including idle, running, paused, and completed sessions.
- A small deterministic fixture proves the additive categories match the
  total, including coordinator work, failed requests, retries, and tool actions.
- Repeated rendering/saving does not double-count. Resume and reload preserve
  the total; a new chat starts at zero. Incomplete historical data is identified.
- Keep the sidebar readable at its normal width; singular and plural labels
  work for zero, one, and large counts.
- Follow [CONTRIBUTING.md](../../CONTRIBUTING.md): use focused frontend and
  lightweight accounting tests. No live inference or new heavy workflow test
  is needed for this counter. Record new-test timing when implemented.
