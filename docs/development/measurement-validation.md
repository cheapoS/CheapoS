# Measurement mode validation

September 13, 2026. Measurement is an explicit operator-selected flag bound to the
run plan and authorization. Normal bounded plans retain their current behavior.

Focused evidence:

- A real isolated three-item deterministic run completed checks, independent
  reviews, three feature commits and final readiness despite nominal limits of
  one working second, one worker turn, eight requests and 2,048 review tokens.
  Its execution case passed in 55.110s. This was not live model inference.
- Four small measurement regressions passed: cumulative usage and restart,
  spending enforcement, review reservations, skipped checkpoint intervals,
  no-deadline subprocess checks with cancellation, and immutable mode selection.
- Nine existing ledger tests passed; eleven planner, eight HTTP planning and
  eight cooldown tests passed. The latter set took 21.600s with three processes.
- All 89 JavaScript tests and syntax checks passed. A disposable browser fixture
  exercised the measurement checkbox, its boolean planning payload, proposal
  label and disclosure showing only the still-active spending/response limits.
- No full Python suite was run. No new live inference run was needed to validate
  these changes; the earlier live qualification remains a bounded historical run.

The initial measurement test batch exposed a missing `uncertain_requests` field
in the synthetic unit fixture. It was corrected and only the four small tests
were repeated; the passing three-item integration was not rerun.

The ledger now includes worker-token totals and accumulated check duration, and
branch execution records observed model outcomes in the existing local pool.
These preserve estimates and pending reservations rather than claiming a provider
billing receipt. Mode selection does not bypass command consent, evidence-bound
review, branch ownership, explicit merge decisions or the selected spending cap.
