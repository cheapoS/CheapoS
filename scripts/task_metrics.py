#!/usr/bin/env python3
"""Export anonymized local task metrics or run deterministic disposable fixtures."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cheapos import metrics, evaluation


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--store',type=Path,help='Explicit local cheapoS data directory; read only')
    choice.add_argument('--benchmark',action='store_true',help='Run seven deterministic disposable fixtures, no live inference')
    choice.add_argument('--trials',type=Path,help='Read a local trial manifest; no model calls')
    parser.add_argument('--markdown',type=Path,help='Optional comparison Markdown destination (requires --trials)')
    parser.add_argument('--output',type=Path,required=True,help='Local JSON destination')
    args=parser.parse_args(argv)
    if args.markdown and not args.trials: parser.error('--markdown requires --trials')
    if args.trials:
        try:
            manifest=json.loads(args.trials.read_text())
            sources=[args.trials.resolve(), *[(args.trials.parent / entry['source']).resolve() for entry in manifest['trials']]]
            destinations=[args.output.resolve()] + ([args.markdown.resolve()] if args.markdown else [])
            def same_file(left, right):
                return left == right or left.exists() and right.exists() and left.samefile(right)
            if any(same_file(left, right) for i, left in enumerate(destinations)
                   for right in [*sources, *destinations[i+1:]]):
                parser.error('Report destinations must differ from each other and every input file')
            report=evaluation.report(manifest,args.trials.parent)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            parser.error('Invalid trial manifest or source snapshot; see the local trial schema documentation')
    elif args.benchmark:
        from cheapos.benchmark import run
        report=run()
    else:
        if not (args.store/'tasks').is_dir():parser.error('The selected store has no tasks directory')
        tasks=[json.loads(path.read_text()) for path in sorted((args.store/'tasks').glob('*/task.json'))]
        report=metrics.export(tasks)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    if args.markdown:
        args.markdown.parent.mkdir(parents=True,exist_ok=True)
        args.markdown.write_text(evaluation.markdown(report),encoding='utf-8')
    print('Local report written. No prompts, source paths, raw outputs or credentials are included.')
    return 0


if __name__=='__main__':raise SystemExit(main())
