"""PromptDiet: utilities for prompt token minimization and fluff reduction.

This module provides simple heuristic functions for estimating token count, detecting common filler phrases, analysing prompts, minifying them by removing fluff and redundant markdown, and generating unified diffs.

The implementation is intentionally lightweight and relies only on the Python standard library.
"""

import re
import difflib
from typing import List, Dict

# --- Token estimation -------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Return an approximate token count.

    The heuristic assumes roughly one token per four characters, which is close
    to the behaviour of OpenAI's GPT‑3 tokeniser for English text.

    Args:
        text: The input string.

    Returns:
        The estimated number of tokens as an integer.
    """
    # Count characters including whitespace. Avoid division by zero.
    if not text:
        return 0
    return len(text) // 4

# --- Fluff detection --------------------------------------------------------

# List of simple filler phrases. In a real implementation this could be
# extended or replaced with a language model.
_FUFF_PHRASES = [
    "I hope you are doing well",
    "just to let you know",
    "thank you for your time",
    "please let me know",
    "just a quick note",
]

# Regular expression to detect bold/italic markdown.
_RE_MARKDOWN = re.compile(r"(\*\*|__)(.*?)\1")

# Regular expression to collapse multiple newlines.
_RE_MULTILINE = re.compile(r"\n{3,}")

# Regular expression for leading/trailing whitespace.
_RE_WS = re.compile(r"^\s+|\s+$")


def detect_fluff(text: str) -> List[str]:
    """Detect common filler phrases in the prompt.

    Args:
        text: Prompt text.

    Returns:
        List of detected fluff phrases present in the text.
    """
    found = []
    for phrase in _FUFF_PHRASES:
        if phrase.lower() in text.lower():
            found.append(phrase)
    return found

# --- Analysis ---------------------------------------------------------------

def analyze(text: str) -> Dict[str, object]:
    """Return a dictionary containing analysis of a prompt.

    The dictionary contains:

    - ``tokens``: estimated token count
    - ``fluff``: list of detected fluff phrases
    - ``savings``: estimated token savings if the prompt were minified
    """
    tokens = estimate_tokens(text)
    fluff = detect_fluff(text)
    minified = minify(text)
    savings = tokens - estimate_tokens(minified)
    return {"tokens": tokens, "fluff": fluff, "savings": savings}

# --- Minification -----------------------------------------------------------

def _remove_fluff(text: str) -> str:
    """Remove any of the known fluff phrases from the text."""
    for phrase in _FUFF_PHRASES:
        # Remove case-insensitive occurrences
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        text = pattern.sub("", text)
    return text


def _collapse_markdown(text: str) -> str:
    """Remove simple markdown formatting such as bold and italics.

    The function also collapses excessive newlines.
    """
    # Remove bold/italic markers
    text = _RE_MARKDOWN.sub(r"\2", text)
    # Collapse multiple newlines into two
    text = _RE_MULTILINE.sub("\n\n", text)
    # Trim leading/trailing whitespace on each line
    lines = [ _RE_WS.sub("", line) for line in text.splitlines() ]
    return "\n".join(line for line in lines if line)


def minify(text: str) -> str:
    """Return a cleaned version of *text*.

    The minification removes known fluff phrases, collapses redundant markdown
    and normalises whitespace.
    """
    without_fluff = _remove_fluff(text)
    collapsed = _collapse_markdown(without_fluff)
    return collapsed

# --- Diff ---------------------------------------------------------------

def diff(original: str, minified: str) -> str:
    """Return a unified diff string between *original* and *minified*.

    The diff uses ``difflib.unified_diff`` with a context of 3 lines.
    """
    original_lines = original.splitlines(keepends=True)
    minified_lines = minified.splitlines(keepends=True)
    diff_lines = difflib.unified_diff(
        original_lines, minified_lines,
        fromfile="original",
        tofile="minified",
        lineterm=""
    )
    return "\n".join(diff_lines)

