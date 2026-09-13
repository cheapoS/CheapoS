#!/usr/bin/env python3
"""Offline experiment against an existing OmniRoute installation; never installs."""
import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cheapos import check_output
from cheapos.benchmark import run

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway-package',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    package=args.gateway_package.resolve()
    manifest=json.loads((package/'package.json').read_text())
    if manifest.get('name')!='omniroute':raise ValueError('Expected existing OmniRoute package')
    source=package/'open-sse/services/compression/engines/headroom'
    captures=[];original=check_output.messages
    def observe(task,messages,config):
        transformed,info=original(task,messages,config)
        captures.append(copy.deepcopy({'raw':messages,'concise':transformed}))
        return transformed,info
    with patch.object(check_output,'messages',side_effect=observe):
        fixture_report=run(output_filter=True)
        noisy_report=run(output_filter=True,verbose=True,only='f03')
    with tempfile.TemporaryDirectory(prefix='cheapos-context-probe-') as directory:
        root=Path(directory);modules=root/'headroom'
        shutil.copytree(source,modules)
        (root/'node_modules').symlink_to(package/'node_modules',target_is_directory=True)
        (root/'package.json').write_text('{"type":"module"}')
        (root/'input.json').write_text(json.dumps(captures))
        subprocess.run(['node',str(Path(__file__).with_name('context_compression_probe.mjs')),str(root/'input.json'),str(root/'result.json'),str(modules)],check=True,timeout=30)
        result=json.loads((root/'result.json').read_text())
    result['versions']={'omniroute':manifest['version'],'license':manifest['license'],'node':subprocess.check_output(['node','--version'],text=True).strip(),'toon':json.loads((package/'node_modules/@toon-format/toon/package.json').read_text())['version']}
    result['source_sha256']={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source.rglob('*.ts'))}
    result['fixture_runs']={'baseline_seven_passed':fixture_report['passed'],'noisy_passed':noisy_report['passed'],'source_hashes':[f['baseline_sha256'] for f in fixture_report['fixtures']+noisy_report['fixtures']]}
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(result['decision'])
if __name__=='__main__':main()
