# T44 observation: compaction renewed repeated-read allowance

During the frozen first exporter attempt, the observer saw repeated source/spec
reads and frequent context compaction before the first implementation write.
At one saved observation there were 17 worker requests, 12 compactions, no patch,
and one repeated-read warning. The current snapshot alone was 46,461 characters;
ordinary subsequent tool exchanges could reach the 60,000-character compaction
threshold quickly. Request 18 began a write, so this is not evidence that the
attempt would never progress.

`Engine.compact_context()` cleared the path/content-hash observation map and
reseeded snapshot files with zero repeats. A tiny deterministic reproduction
returned `[2, 2, 2, 2]` for identical reads separated by compactions; without
another compaction, the next read reached the stop threshold of 3. Files omitted
from the bounded snapshot lost their observation history as well.

The narrow repair retains the map and unions supplied snapshot lines into each
existing path/hash entry without resetting its repeat count. Changed hashes and
previously unseen lines still count as new evidence. Existing lifecycle resets
for real edits and new work remain unchanged. This fixes the repeated-read
allowance; it does not redesign context selection or promise model progress.

The repair was developed separately from the live application and candidate,
from commit `0c33759`, for integration only after the frozen attempt. It contains
no exporter implementation or live-task modifications.

Validation: inspected the change selector (the shared engine import fans out to
57 modules) and chose the directly affected modules instead of a broad run:

```sh
python3 -B scripts/dev_tests.py --pattern test_compaction_observations.py \
  --pattern test_compact_edits.py --pattern test_progress_recovery.py \
  --jobs 3 --timings
```

All 26 tests passed in 9.098 seconds wall time. The two new deterministic tests
use no Git repository, subprocess, provider, or sleep and measured below the
runner's 0.001-second display precision (reported 0.000s combined). They cover
repeats through compaction/omission, retained ranges, new lines, and changed
hashes. Existing compact-edit and progress-recovery coverage passed unchanged.
`git diff --check` passes. No full suite, inference, or browser run was added.
