"""Robust context-anchored code block matching and multi-chunk editing."""

import ast
import difflib
import re


class EditMatchError(ValueError):
    """Base error for edit matching failures with actionable diagnostics."""

    def __init__(self, message, code=None, details=None):
        super().__init__(message)
        self.code = code or "edit_match_error"
        self.details = details or {}


class TargetNotFoundError(EditMatchError):
    """The target block was not found in the file."""

    def __init__(self, message, details=None):
        super().__init__(message, code="target_not_found", details=details)


class TargetAmbiguousError(EditMatchError):
    """The target block matches multiple locations in the file."""

    def __init__(self, message, details=None):
        super().__init__(message, code="target_ambiguous", details=details)


class OverlappingChunksError(EditMatchError):
    """Two or more edit chunks overlap in the same file region."""

    def __init__(self, message, details=None):
        super().__init__(message, code="overlapping_chunks", details=details)


class SyntaxValidationError(EditMatchError):
    """The edit produces invalid syntax."""

    def __init__(self, message, details=None):
        super().__init__(message, code="syntax_error", details=details)


def _line_number_at_offset(text, offset):
    """Return 1-indexed line number at character offset."""
    return text.count("\n", 0, offset) + 1


def _find_exact_matches(content, target):
    """Find all exact character start offsets of target in content."""
    matches = []
    start = 0
    while True:
        pos = content.find(target, start)
        if pos == -1:
            break
        matches.append((pos, pos + len(target)))
        start = pos + 1
    return matches


def _normalize_trailing_ws(text):
    """Normalize line endings to LF and strip trailing whitespace on each line."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines)


def _find_whitespace_resilient_matches(content, target):
    """Match lines while ignoring trailing whitespace and uniform line endings."""
    norm_content = _normalize_trailing_ws(content)
    norm_target = _normalize_trailing_ws(target)

    if not norm_target.strip():
        return []

    # Preserve original line lengths for exact character offsets
    content_lines = content.splitlines(keepends=True)
    target_lines = norm_target.splitlines()

    if not target_lines or not content_lines:
        return []

    stripped_c_lines = [line.rstrip("\r\n").rstrip() for line in content_lines]
    t_len = len(target_lines)

    matches = []
    for i in range(len(stripped_c_lines) - t_len + 1):
        if stripped_c_lines[i : i + t_len] == target_lines:
            # Calculate character offset in original content
            start_offset = sum(len(line) for line in content_lines[:i])
            end_offset = sum(len(line) for line in content_lines[: i + t_len])
            # If the last target line didn't have a trailing newline, don't include trailing newline of content line
            if not target.endswith(("\n", "\r")):
                # exclude trailing newline from end_offset if content line had one
                orig_last = content_lines[i + t_len - 1]
                nl_len = len(orig_last) - len(orig_last.rstrip("\r\n"))
                end_offset -= nl_len
            matches.append((start_offset, end_offset))

    return matches


def _find_closest_candidate(content, target, max_lines_scan=200):
    """Locate the closest matching block in content and generate a helpful diff hint."""
    target_clean = _normalize_trailing_ws(target).strip()
    target_lines = target_clean.splitlines()
    if not target_lines:
        return None

    content_clean = _normalize_trailing_ws(content)
    content_lines = content_clean.splitlines()
    if not content_lines:
        return None

    t_len = len(target_lines)
    best_ratio = 0.0
    best_idx = 0
    target_joined = "\n".join(target_lines)

    # Slide a window of size t_len (and +/- 2 lines)
    window_sizes = sorted(set(filter(lambda x: x > 0, [t_len, t_len - 1, t_len + 1, t_len - 2, t_len + 2])))
    matcher = difflib.SequenceMatcher(None, "", "")
    matcher.set_seq2(target_joined)

    for w_size in window_sizes:
        if w_size > len(content_lines):
            continue
        for i in range(len(content_lines) - w_size + 1):
            window = "\n".join(content_lines[i : i + w_size])
            matcher.set_seq1(window)
            # Quick check
            if matcher.real_quick_ratio() < 0.4:
                continue
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = i
                t_len = w_size

    if best_ratio >= 0.5:
        candidate_lines = content_lines[best_idx : best_idx + t_len]
        diff = list(
            difflib.unified_diff(
                candidate_lines,
                target_lines,
                fromfile=f"file_lines_{best_idx + 1}_{best_idx + t_len}",
                tofile="target_lines",
                lineterm="",
            )
        )
        return {
            "start_line": best_idx + 1,
            "end_line": best_idx + t_len,
            "similarity": round(best_ratio * 100, 1),
            "candidate": "\n".join(candidate_lines),
            "diff": "\n".join(diff),
        }

    return None


def match_chunk(content, target):
    """Find the single unique span (start, end) for target in content.

    Raises:
        TargetNotFoundError: if target matches 0 times (includes nearest match diagnostics).
        TargetAmbiguousError: if target matches >1 times (includes line numbers).
    """
    if not target:
        raise TargetNotFoundError("Target block cannot be empty.")

    # 1. Exact match attempt
    matches = _find_exact_matches(content, target)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        lines = [_line_number_at_offset(content, m[0]) for m in matches]
        raise TargetAmbiguousError(
            f"Target block matches {len(matches)} times at lines {lines}. "
            "Add 1–3 lines of surrounding context to make the target block unique.",
            details={"match_count": len(matches), "lines": lines},
        )

    # 2. Whitespace-resilient match attempt
    ws_matches = _find_whitespace_resilient_matches(content, target)
    if len(ws_matches) == 1:
        return ws_matches[0]
    if len(ws_matches) > 1:
        lines = [_line_number_at_offset(content, m[0]) for m in ws_matches]
        raise TargetAmbiguousError(
            f"Target block (with whitespace normalization) matches {len(ws_matches)} times at lines {lines}. "
            "Add 1–3 lines of surrounding context to make the target block unique.",
            details={"match_count": len(ws_matches), "lines": lines},
        )

    # 3. Target not found: compute diagnostic hint
    hint = _find_closest_candidate(content, target)
    if hint:
        msg = (
            f"Target block not found. Closest match found at lines {hint['start_line']}–{hint['end_line']} "
            f"({hint['similarity']}% match).\n"
            f"Differences:\n{hint['diff']}\n\n"
            "Update 'target' to match the actual file contents."
        )
        raise TargetNotFoundError(msg, details={"closest_match": hint})

    raise TargetNotFoundError(
        "Target block not found in file. Check the file contents with read_file before editing.",
        details={},
    )


def apply_chunks(content, chunks, filename=None):
    """Apply one or more replacement chunks to content atomically.

    Each chunk must be a dict with:
        'target': existing string to replace
        'replacement': new string to substitute

    Raises:
        TargetNotFoundError, TargetAmbiguousError, OverlappingChunksError, SyntaxValidationError
    """
    if isinstance(chunks, dict):
        chunks = [chunks]

    if not chunks:
        return content, 0

    resolved_spans = []
    for idx, chunk in enumerate(chunks):
        if not isinstance(chunk, dict) or "target" not in chunk or "replacement" not in chunk:
            raise EditMatchError(
                f"Chunk #{idx + 1} must be an object with 'target' and 'replacement' string properties."
            )
        target = chunk["target"]
        replacement = chunk["replacement"]
        if not isinstance(target, str) or not isinstance(replacement, str):
            raise EditMatchError(f"Chunk #{idx + 1} 'target' and 'replacement' must be strings.")

        start, end = match_chunk(content, target)
        resolved_spans.append((start, end, replacement, idx))

    # Check for overlaps
    sorted_spans = sorted(resolved_spans, key=lambda x: x[0])
    for i in range(len(sorted_spans) - 1):
        curr_start, curr_end, _, curr_idx = sorted_spans[i]
        next_start, next_end, _, next_idx = sorted_spans[i + 1]
        if curr_end > next_start:
            curr_line = _line_number_at_offset(content, curr_start)
            next_line = _line_number_at_offset(content, next_start)
            raise OverlappingChunksError(
                f"Chunk #{curr_idx + 1} (line {curr_line}) overlaps with chunk #{next_idx + 1} (line {next_line}). "
                "Combine them into a single contiguous chunk or separate them into non-overlapping regions.",
                details={"chunk_a": curr_idx + 1, "chunk_b": next_idx + 1},
            )

    crlf_mode = "\r\n" in content and content.count("\r\n") >= content.count("\n") // 2

    # Apply bottom-up (descending by start offset) so character indices don't shift
    modified = content
    for start, end, replacement, _ in sorted(resolved_spans, key=lambda x: x[0], reverse=True):
        if crlf_mode and "\n" in replacement and "\r\n" not in replacement:
            replacement = replacement.replace("\n", "\r\n")
        modified = modified[:start] + replacement + modified[end:]

    # Syntax check for Python files if filename is supplied
    if filename and filename.endswith(".py"):
        try:
            ast.parse(modified, filename=filename)
        except SyntaxError as err:
            raise SyntaxValidationError(
                f"Edit rejected: resulting code has Python syntax error on line {err.lineno}: {err.msg}\n"
                f"{err.text or ''}",
                details={"lineno": err.lineno, "msg": err.msg, "text": err.text},
            )

    return modified, len(resolved_spans)
