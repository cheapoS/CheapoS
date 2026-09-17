#!/usr/bin/env python3
"""Count lines, words, and characters in a file or stdin."""

import argparse
import json
import sys


def count(text):
    """Return (lines, words, chars) for the given text."""
    if text == "":
        return 0, 0, 0
    lines = text.count("\n")
    if not text.endswith("\n"):
        lines += 1
    words = len(text.split())
    chars = len(text)
    return lines, words, chars


def main():
    parser = argparse.ArgumentParser(description="Count lines, words, and characters.")
    parser.add_argument("path", nargs="?", help="File path (default: stdin)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.path:
        try:
            with open(args.path, "r", encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            print(f"Error: File '{args.path}' not found.", file=sys.stderr)
            sys.exit(1)
    else:
        text = sys.stdin.read()
    lines, words, chars = count(text)

    if args.json:
        print(json.dumps({"lines": lines, "words": words, "characters": chars}))
    else:
        print(f"{lines} {words} {chars}")


if __name__ == "__main__":
    main()
