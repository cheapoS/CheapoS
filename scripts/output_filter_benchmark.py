#!/usr/bin/env python3
"""Deterministic comparison; no inference, credentials, or installed dependencies."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cheapos.benchmark import run

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result={}
    for name,filtered,retrieve in [('raw',False,False),('filtered',True,False),('filtered_retrieval',True,True)]:
        result[name]=run(output_filter=filtered,retrieve=retrieve)
        result['noisy_'+name]=run(output_filter=filtered,retrieve=retrieve,verbose=True,only='f03')
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('24 fixture runs passed; measurements written to',args.output)
