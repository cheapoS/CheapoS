# Public alpha readiness — September 19, 2026

The recommended launch is a **source-install public alpha for trusted personal
repositories**. Start with the scripted demo, then try a small real task. Model
reliability, automatic recovery and conversation quality remain active development
areas; passing deterministic tests does not guarantee every live task completes.

## Release cleanup

- All local requests no longer depend on the remote gateway catalog to select an
  output allowance. Existing no-remote-discovery coverage exercises this path.
- Planning replies use the chat's captured settings. Changing global defaults
  must not reject a reply or silently change that chat's model authority.
- The scripted benchmark handles an unset planner role.
- Packaged apps store data outside the replaceable bundle, in the user's
  application data directory. Source installations and explicit `--data-dir`
  overrides retain their existing behavior.
- Frozen restarts preserve launch options without adding the executable twice.
- macOS release jobs use supported ARM/Intel runners, check binary architecture
  and ad-hoc signatures, and publish prereleases. Bundle version comes from the
  application version. Neither Developer ID signing nor notarization is provided.
- CI runs JavaScript regressions as well as Python tests and syntax checks.
- Fixtures now reflect saved settings, asynchronous startup, task-copy setup and
  explicit legacy budgets. Existing permission, review, Git and evidence assertions
  remain in place. Installed optional Carto tooling cannot index shared test fixtures.
- User/security docs describe current limits, recovery, credential persistence,
  opt-in Club sharing and experimental desktop distribution. Local Markdown file
  links were checked and repaired, including the archived milestone boards.

## Validation

Validation used a disposable source snapshot on macOS Apple Silicon, Python 3.9.6
and Node 26.3.0, without live model requests or the operator's app profile.

Full release command: `python3 -B scripts/check.py --full --jobs 4`.
- **1,482 Python tests passed**, 459.414 seconds with four worker processes.
- **325 JavaScript tests passed**; all frontend JavaScript syntax checks passed.
- `git diff --check` and the local Markdown file-link scan passed.

The four new launcher contract tests use only in-memory state and complete in
under 0.01 seconds together. They cover source storage, native/frozen external
storage, bundle replacement paths, and source/frozen restart arguments. Existing
HTTP planning coverage also verifies that changing global defaults preserves the
saved chat settings and continuation.

A PyInstaller 6.22.3 Apple Silicon app passed executable help, architecture and
ad-hoc signature checks. An isolated temporary HOME/profile then passed startup,
static asset loading, token-authenticated restart and loading the same saved
settings after copying the bundle to a replacement location. Startup greetings
and gateway connections were disabled. DMG creation also completed successfully.
No generated app or DMG is committed to the source repository.

## Remaining release-environment checks

- Run the hosted macOS/Linux Python 3.9/3.13 CI matrix on the committed revision.
  This local run is not evidence for platforms it did not execute.
- Test an Intel build and downloaded app installation/upgrade on a fresh Mac
  before promoting desktop downloads beyond experimental status. The local
  package smoke test does not exercise Gatekeeper download quarantine.
- Verify repository visibility, private vulnerability reporting and the advertised
  security contact in the publishing account. The local GitHub CLI account could
  not read repository metadata or hosted Actions status.

No repository visibility change or release tag is part of this cleanup.

## Launch follow-up — September 19

Rechecked runtime revision `4a64f8c` in a disposable clone. All 1,482 Python
regressions and 325 JavaScript regressions passed across the initial run and a
focused retry. The initial sandbox blocked local HTTP fixture sockets; the five
affected modules (97 tests) passed outside that restriction in 11.793 seconds.
No real model requests or operator profile were used.

GitHub's main-branch run `35473287769` exposed preinstalled Git LFS filters on its
hosted runners. Both CI workflows now remove only the runner's global/system LFS
defaults before tests. Repository-local filters and the application's filter
rejection stay intact. The exact shell step passed a disposable configuration
check for removal, preservation of another filter, and repeated execution.
The hosted matrix still needs a passing run on the resulting commit.

A local credential-pattern scan inspected 3,580 reachable historical blobs
(129 MB), including the three remote branches and release tag. It found no
private-key, provider-key, GitHub-token, AWS-key, JWT or long literal-secret
matches. This is a targeted scan, not a guarantee that history contains no
sensitive information. The historical `pinner.db` sample contains an empty
bookmark table. No history rewrite was performed.
