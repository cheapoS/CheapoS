#!/usr/bin/env python3
"""Export anonymized local task metrics or run deterministic disposable fixtures."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cheapos import metrics


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--store',type=Path,help='Explicit local CheapOS data directory; read only')
    choice.add_argument('--benchmark',action='store_true',help='Run seven deterministic disposable fixtures, no live inference')
    parser.add_argument('--output',type=Path,required=True,help='Local JSON destination')
    args=parser.parse_args()
    if args.benchmark:
        from cheapos.benchmark import run
        report=run()
    else:
        if not (args.store/'tasks').is_dir():parser.error('The selected store has no tasks directory')
        tasks=[json.loads(path.read_text()) for path in sorted((args.store/'tasks').glob('*/task.json'))]
        report=metrics.export(tasks)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('Local report written. No prompts, source paths, raw outputs or credentials are included.')
    return 0


if __name__=='__main__':raise SystemExit(main())
