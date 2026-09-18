"""PromptDiet CLI.

Subcommands: analyze (JSON analysis), minify (minified prompt),
diff (unified diff). Each accepts a --file argument or reads from
stdin. Output is written to stdout.
"""

import argparse
import json
import os
import sys

# Import the sibling module regardless of the working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prompt_diet import analyze, diff, minify  # noqa: E402


def _read_text(args):
    """Read prompt text from args.file, or stdin when omitted."""
    if args.file:
        with open(args.file, "r", encoding="utf-8") as handle:
            return handle.read()
    return sys.stdin.read()


def run_analyze(args):
    print(json.dumps(analyze(_read_text(args)), indent=2))


def run_minify(args):
    print(minify(_read_text(args)))


def run_diff(args):
    text = _read_text(args)
    print(diff(text, minify(text)))

def main():
    parser = argparse.ArgumentParser(
        description="PromptDiet: prompt token minimization and fluff reduction."
    )
    subparsers = parser.add_subparsers(dest="command")

    handlers = {
        "analyze": (run_analyze, "Print a JSON token/fluff/savings analysis."),
        "minify": (run_minify, "Print the minified prompt to stdout."),
        "diff": (run_diff, "Print a unified diff between original and minified."),
    }
    for name, (func, help_text) in handlers.items():
        sub = subparsers.add_parser(name, help=help_text, description=help_text)
        sub.add_argument(
            "--file",
            metavar="PATH",
            default=None,
            help="Path to a prompt file. Reads from stdin when omitted.",
        )
        sub.set_defaults(func=func)

    args = parser.parse_args()

    if not getattr(args, "func", None):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()