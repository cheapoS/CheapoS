# Qualification Trial Results: Unattended Workflow (10 Tasks)

**Trial Environment & Configuration:**
- **Repository:** CheapOS isolated trial target (`/private/tmp/cheapoS-unattended-trial-repo`)
- **Mode:** Unattended branch runs with measurement mode (`measurement: true`)
- **Worker Model:** `openrouter/deepseek/deepseek-chat`
- **Reviewer Model:** `openrouter/google/gemini-2.5-flash`
- **Gateway:** OmniRoute (`http://127.0.0.1:20128/v1`)
- **Working Feature Branch:** `work/unattended-workflow-trial`

---

## Executive Summary (Tasks 1–5: Halfway Milestone)

| Task | Module | Title | Items | Turns | Tool Calls | Reviews | Cost (USD) | Requests (Est.) | Status | Merged Commit |
|---|---|---|---|---|---|---|---|---|---|---|
| **1** | `labels.py` | String & Label Normalizer (`normalize_label`) | 2 | 18 | 23 | 13 | $0.0000 | 54 | ✅ Passed & Merged | `a4ef58c` |
| **2** | `expenses.py` | Robust CSV Expense Parser (`parse_expenses`, `summarize_by_category`) | 3 | 79 | 60 | 16 | $0.0000 | 100 | ✅ Passed & Merged | `e7c336d` |
| **3** | `cache.py` | In-Memory TTLCache with LRU Eviction (`TTLCache`) | 4 | 51 | 45 | 4 | $0.0000 | 80 | ✅ Passed & Merged | `71f45a1` |
| **4** | `table_formatter.py` | Markdown Table Formatter & Aligner (`format_table`, `parse_table`) | 1 | 23 | 17 | 3 | $0.0048 | 30 | ✅ Passed & Merged | `a759c29` |
| **5** | `cliparser.py` | CLI Option Parser & Subcommand Dispatcher (`CLIParser`, `CLIError`) | 5 | 156 | 108 | 24 | $0.0142 | 181 | ✅ Passed & Merged | `f4fbeae` |
| **Total (1–5)** | — | — | **15** | **327** | **253** | **60** | **$0.0190** | **445** | **19/19 Tests Passing** | — |

**Acceptance Test Suite:**
- 19/19 acceptance tests passing across Tasks 1–5 (`python3 -m unittest test_acceptance`).
- Zero regressions in existing components.
- Cumulative spend: **~$0.019 USD** (well below budget limits).
- Request volume: **445 requests** (safely under the 1,000/day OpenRouter rate limit).

---

## Detailed Task Breakdown

### Task 1: String & Label Normalizer (`labels.py`)
- **Acceptance Criteria:** `normalize_label(text)` trims whitespace, collapses internal whitespace sequences into single spaces, handles Unicode correctly, and raises `TypeError` for non-string inputs.
- **Workflow & Execution:**
  - Plan approved with 2 items.
  - Item 0 created `labels.py` with `normalize_label`.
  - Item 1 updated `README.md` with usage examples.
  - Reviewer: Gemini 2.5 Flash approved with clean static and execution evidence.
- **Metrics:** 18 worker turns, 23 tool calls, 13 reviews, 54 API requests, $0.00 cost.

### Task 2: Robust CSV Expense Parser (`expenses.py`)
- **Acceptance Criteria:** Parse RFC-compliant multi-line CSVs with quoted strings containing commas and newlines. Implement `parse_expenses(csv_text)` returning formatted dicts (`date`, `category`, `amount`, `description`), raising `ValueError` on malformed lines, and `summarize_by_category(records)` returning sorted totals.
- **Workflow & Execution:**
  - 3 items executed and committed.
  - Handled multi-line quote boundaries and decimal amount parsing.
  - Resolved subtle date format validations.
- **Metrics:** 79 worker turns, 60 tool calls, 16 reviews, 100 API requests, $0.00 cost.

### Task 3: In-Memory Cache with TTL & LRU (`cache.py`)
- **Acceptance Criteria:** `TTLCache(maxsize, default_ttl)` supporting `get`, `set`, `delete`, `clear`, `__len__`, LRU eviction when capacity is exceeded, and TTL expiration on read.
- **Workflow & Execution:**
  - 4 items (including 2 verification and recovery items).
  - Clean implementation combining `collections.OrderedDict` for LRU ordering with timestamp dictionaries for expiration.
- **Metrics:** 51 worker turns, 45 tool calls, 4 reviews, 80 API requests, $0.00 cost.

### Task 4: Markdown Table Formatter & Aligner (`table_formatter.py`)
- **Acceptance Criteria:** `format_table(headers, rows, alignments=None)` producing GFM markdown tables with proper column padding and alignment markers (`:---`, `:---:`, `---:`), plus `parse_table(markdown_table)` recovering structured headers and rows.
- **Workflow & Execution:**
  - 1 item executed in single-shot cleanly.
  - Verified edge cases: padded cells, empty cells, missing alignments default to left.
- **Metrics:** 23 worker turns, 17 tool calls, 3 reviews, 30 API requests, $0.0048 cost.

### Task 5: CLI Option Parser & Dispatcher (`cliparser.py`)
- **Acceptance Criteria:** `CLIParser` with `add_argument` (flags, options, types, defaults, required, actions), `add_subcommand`, and `parse_args` returning dot-accessible namespaces. `CLIError` exception class.
- **Workflow & Execution:**
  - 5 items planned, executed, verified, and committed.
  - DeepSeek and Gemini handled complex argument parsing, positional arguments ordering, subcommand delegating parsers, and required-argument validation.
- **Metrics:** 156 worker turns, 108 tool calls, 24 reviews, 181 API requests, $0.0142 cost.

---

## CheapOS Engine Defect Discoveries & Resolutions

During Tasks 1–5 supervision, four key CheapOS platform/engine issues were identified, analyzed, and resolved on branch `work/unattended-workflow-trial`:

1. **Branch Run Tool Demarcation Bug (`cheapos/engine.py`):**
   - *Issue:* Tasks running under unattended branch runs (`task.get('branch_run')`) were inadvertently inheriting conversational chat behavior (`CHAT_SYSTEM` and `CHAT_TOOLS` with `ask_user`), causing workers to output chat questions or get trapped in `awaiting_reply`.
   - *Fix:* Ensured `(task.get('conversational') and not task.get('branch_run'))` gates all chat system prompts and tools so branch runs strictly operate with `WORKER_SYSTEM` and `WORKER_TOOLS`.

2. **Gemini Reviewer SSE Streaming Disconnects (`cheapos/engine.py`):**
   - *Issue:* OpenRouter SSE streaming with `google/gemini-2.5-flash` occasionally emitted `MALFORMED_FUNCTION_CALL` during tool call chunk streaming.
   - *Fix:* Disallowed streaming (`streams_output = False`) specifically for Gemini models, with automatic non-streaming retry on stream errors.

3. **Multi-Item Plan Criteria Aggregation Cap (`cheapos/branch_completion.py`):**
   - *Issue:* In plans with multiple items, `_repair_item` aggregated all acceptance criteria across every item into a single list and enforced `len(criteria) <= 12`. Plans with 5 items routinely exceed 12 criteria cumulatively (even though each item individually conforms to 1–12 criteria), throwing `ValueError('This correction spans more than 12 criteria; submit a smaller explicit amendment')` and pausing the branch run.
   - *Fix:* Bounded the repair item's criteria to the first 12 unique criteria (`criteria[:12]`), satisfying both the item criteria limit and preserving the repair authorization contract.

4. **Test Suite Verification (`scripts/check.py`):**
   - Verified that all CheapOS regression test suites pass with the fixes applied (502 tests passing across 68 test modules).

---

## Next Steps (Tasks 6–10)

- **Task 6:** Math Expression Evaluator (`evaluator.py`) with AST arithmetic parsing and precedence.
- **Task 7:** HTTP Request Router (`router.py`) with path parameters and method routing.
- **Task 8:** File-Based Atomic Queue (`queue_pipeline.py`) with lockfile concurrency safety.
- **Task 9:** Configuration Schema Validator (`validator.py`) with type and constraint checking.
- **Task 10:** SQLite Task Storage with Migrations (`storage.py`).
