import sys
import argparse
import json
from examples.prompt_diet.prompt_diet import analyze, minify, diff

def run_analyze(args):
    with open(args.file, 'r') as f:
        text = f.read()
    result = analyze(text)
    print(json.dumps(result, indent=2))

def run_minify(args):
    with open(args.file, 'r') as f:
        text = f.read()
    minified = minify(text)
    print(minified)

def run_diff(args):
    with open(args.file, 'r') as f:
        text = f.read()
    minified = minify(text)
    print(diff(text, minified))

def main():
    parser = argparse.ArgumentParser(description="PromptDiet CLI")
    subparsers = parser.add_subparsers(dest="command")

    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("file", help="Input prompt file")

    minify_parser = subparsers.add_parser("minify")
    minify_parser.add_argument("file", help="Input prompt file")

    diff_parser = subparsers.add_parser("diff")
    diff_parser.add_argument("file", help="Input prompt file")

    args = parser.parse_args()

    if args.command == "analyze":
        run_analyze(args)
    elif args.command == "minify":
        run_minify(args)
    elif args.command == "diff":
        run_diff(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
