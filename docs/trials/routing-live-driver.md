# T48 routing qualification observer

Use an external trial directory and an isolated profile configured under T46.
The app/source checkout must be clean and committed. This driver copies only
config.json, preferences.json and gateway.json (including opaque connection
revision and exact included-model grants) into private trial state. It never
changes the app checkout or an operator task.

```sh
python3 -B docs/trials/routing_live.py --prepare --root /tmp/routing-trial-1 --config-dir /tmp/routing-profile
```

Prepare creates the exact `matrix.run_live.fixture('easy')` acceptance bytes and
one operator-prepared proposal. It performs no model planning/inference and does
not authorize Start. Inspect `proposal.private.json`, including the exact access
policy, models, measurement mode, zero paid budget and check commands. Then use
the inspected digest explicitly:

```sh
python3 -B docs/trials/routing_live.py --start --root /tmp/routing-trial-1 --reviewed-digest REVIEWED_SHA256
```

Start requires a fresh proposal with the identical contract/digest. Automatic
remote execution is required; pinned-only, local and delegate fallback are
rejected. T46 performs exact included/public-free eligibility and preserves
reviewer separation. There is one exclusive Start intent: no silent retry,
Resume, reauthorization, merge or push. An interrupted attempt remains evidence.

Baseline freezes app commit/runtime, fixture/tests and private access/config
hashes. Final verification uses matching completed receipts, actual commit
objects/parents/trees, unchanged main and supplied tests, plus a fresh controller
merge preview (which validates saved exact checks/readiness). It does not rerun
unchanged checks. README behavior still requires the observing operator's narrow
example inspection; `qualified` here denotes controller/immutability checks,
not independent proof of every behavioral requirement.

`result.json` contains allowlisted status, model IDs, request/accounted usage,
routing fields, checks and integrity findings. Raw task/proposal/error detail
stays only in mode-0600 private artifacts; never commit those artifacts or copied
configuration. Accounted cost is not a billing receipt. The observer must retain
attempts and explicitly describe interruptions and independent correctness gaps.
No live call occurs for `--help`, syntax checks or helper inspection.
