#!/usr/bin/env python3
"""Install only cheapoS's optional Carto runtime; never run carto init."""
import os
from pathlib import Path
import shutil
import subprocess

root=Path(__file__).resolve().parent.parent/'integrations'/'carto'
npm=shutil.which('npm')
if not npm:raise SystemExit('Install Node.js/npm first, then run this script again.')
subprocess.run([npm,'ci','--prefix',str(root/'runtime'),'--no-audit','--no-fund'],check=True)
env={**os.environ,'PATH':str(root/'runtime'/'node_modules'/'node'/'bin')+os.pathsep+os.environ.get('PATH',''),'CARTO_NO_POSTINSTALL':'1'}
subprocess.run([npm,'ci','--prefix',str(root),'--legacy-peer-deps','--no-audit','--no-fund'],env=env,check=True)
print('Carto installed. Enable it under project menu → Project context. No app restart required.')
