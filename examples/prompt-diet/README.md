# PromptDiet

PromptDiet is a zero-cost CLI and library for prompt token minimization and
fluff reduction. It analyzes prompts and system instructions, detects
redundant qualifiers, verbose filler phrases, redundant markdown formatting,
and unnecessary pleasantries, then proposes a minified alternative along with
an estimated token savings figure. No external dependencies or network calls
are required; everything runs on the Python standard library.

## Features

- **Token estimation** — approximates token count using a 4-character-per-token
  heuristic, which is a close match for standard BPE tokenizers (e.g.
  OpenAI's GPT-3 family) on typical English text.
- **Fluff detection** — finds common filler phrases and pleasantries such as
  "I hope you are doing well", "just to let you know", "please let me know",
  "thank you for your time", and "just a quick note".
- **Redundant markdown detection** — identifies superfluous emphasis markers
  (`**bold**`, `_italic_`) and excessive whitespace that add tokens without
  adding meaning.
- **Minification** — removes detected filler phrases, collapses redundant
  markdown emphasis, and normalizes whitespace, preserving the prompt's core
  semantic intent.
- **Savings estimation** — reports the original token count, the fluff items
  found, and the estimated tokens saved by the minified version.
- **Semantic intent preservation** — minification only strips phrases that map
  onto known filler patterns; direct instructions and substantive content are
  left intact, and the diff output lets you verify what was removed.
- **Unified diff** — produces a `difflib.unified_diff` between the original
  and minified prompt so changes can be inspected.

## Installation

Requires Python 3.9+ and only the standard library. No packages to install.

```bash
cd examples/prompt-diet
```

## Usage

### CLI

The `diet.py` script provides three subcommands:

```bash
# Analyze a prompt file: prints JSON with tokens, fluff items, and savings
python3 diet.py analyze prompt.txt

# Minify a prompt file: prints the cleaned prompt
python3 diet.py minify prompt.txt

# Show a diff: prints the unified diff between original and minified
python3 diet.py diff prompt.txt
```

Each command takes a single argument: the path to a text file containing the
prompt to process. Output is written to stdout.

### Library

```python
from prompt_diet import analyze, minify, diff, detect_fluff, estimate_tokens

analysis = analyze("I hope you are doing well. Please summarize this.")
print(analysis["tokens"])     # estimated token count
print(analysis["fluff"])      # list of detected filler phrases
print(analysis["savings"])    # estimated tokens saved

minified = minify("I hope you are doing well. Please summarize this.")
print(diff(original=minified, minified=minified))
```

### Sample benchmarks

`sample_prompts.json` contains a small benchmark set of prompts with two
deliberately verbose examples (`chatty_summary`, `polite_code_review`) and one
already-minified baseline (`bare_minimum`). You can run the CLI on any of them
after extracting the `prompt` field to a text file, or use them as fixtures
for custom benchmarks.

## Testing

Run the deterministic unit tests with:

```bash
python3 -m unittest examples/prompt-diet/test_diet.py
```

The tests cover token estimation, fluff detection, minification, and diff
output.

## Design notes

- **Zero cost** — no API calls, no model inference, no third-party packages.
- **Deterministic** — all heuristics are pure functions; the token estimator,
  fluff detector, minifier, and diff producer return identical output for
  identical input.
- **Heuristic, not perfect** — the filler list is intentionally conservative.
  Extend `_FUFF_PHRASES`, the markdown regex, and the whitespace collapse rule
  in `prompt_diet.py` to match your organisation's prompt style. Minification
  removes only recognised filler, so core task instructions are preserved by
  construction.