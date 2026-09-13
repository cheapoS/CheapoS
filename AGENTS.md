# Repository workflow

After completing and validating changes, commit your work before handing the project back. cheapoS workers also commit to this repository, and unrelated uncommitted changes can block their commit flow.

Stage only the changes you made for the current task. Preserve any unrelated user or worker changes; do not include, discard, or overwrite them just to make the working tree clean. If they prevent completion, explain what remains.

# Validation while iterating

Follow the current change-scoped policy in CONTRIBUTING.md. Start with
`python3 -B scripts/check.py --plan` and run the relevant checks. UI-only and
documentation-only changes do not require the full Python suite. A routine merge
is not a reason to repeat unchanged passing checks. Historical task cards that
say to run every test before every integration do not override this policy.
Use the full suite only for an explicit comprehensive check, a release, or broad
backend risk that focused tests cannot cover; explain that choice. Preserve
meaningful assertions and product verification/permission safeguards.
