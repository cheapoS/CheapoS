"""Read-only, conservative verification prerequisites; never imports project code."""
import os
import re
import shlex
import shutil
from pathlib import Path

from .workspace import Workspace


def guidance(task):
    workspace=Workspace(task['workspace']);names=workspace.list_files();commands=[];sources=[]
    for name in ('AGENTS.md','CONTRIBUTING.md','README.md'):
        if name not in names:continue
        try:content=workspace.read_file(name,1,200)['content']
        except (ValueError,OSError,UnicodeError):continue
        for line in content.splitlines():
            text=line.partition(': ')[2].strip().strip('`')
            try:argv=shlex.split(text)
            except ValueError:continue
            safe=(len(argv)==4 and argv[0] in {'python','python3'} and argv[1:3]==['-m','venv'] and argv[3] in {'.venv','venv'})
            safe=safe or (len(argv)==6 and argv[0] in {'.venv/bin/python','venv/bin/python','.venv/Scripts/python.exe'} and argv[1:5]==['-m','pip','install','-r'] and argv[5] in names and Path(argv[5]).name.startswith('requirements'))
            if safe and text not in commands:commands.append(text);sources.append({'path':name,'line':line.partition(':')[0]})
            if len(commands)>=3:return commands,sources
    return commands,sources


def inspect(task,argv):
    from .check_specs import cwd
    root=cwd(task, allow_missing=True);value=argv[0]
    found=shutil.which(value) if '/' not in value and '\\' not in value else None
    selected=Path(value) if Path(value).is_absolute() else root/value if '/' in value or '\\' in value else Path(found) if found else None
    state={'version':1,'status':'ready','workspace':task['workspace'],'directory':str(root),'command':list(argv),'missing':None,
           'evidence':'Only directly observable prerequisites were inspected; installed dependencies and test correctness are otherwise unverified.',
           'next_step':'Run the selected verification command with its normal permission checks.','setup_commands':[],'sources':[]}
    from .command_backend import captured, available, executable, descriptor
    backend = captured(task)
    state['execution_environment'] = descriptor(backend)
    try:
        available(backend)
    except ValueError as error:
        state.update(status='missing', missing='command_backend', evidence=str(error),
                     next_step='The operator must provide the selected Linux backend; no host fallback or installation is authorized.')
        return state
    if backend != 'host':
        found = executable(value, Path(task['workspace']).resolve(), root)
        selected = Path(found) if found else None
    if not root.is_dir():
        state.update(status='missing', missing='directory', evidence='The verification working directory does not exist: '+task.get('check_directory', '.'), next_step='Create the planned component in this task copy before running its checks.')
    elif selected is None or not selected.is_file() or not os.access(selected,os.X_OK):
        environment=any(part in {'.venv','venv'} for part in Path(value).parts)
        state.update(status='missing',missing='selected_environment' if environment else 'executable',
                     evidence=f'The selected {"environment executable" if environment else "executable"} is absent or not executable: {value}',
                     next_step='Prepare an environment inside the task copy, or select an available verification executable. Re-check before resuming.')
    elif '-m' in argv and argv[argv.index('-m')+1:argv.index('-m')+2]==['pytest']:
        prefix=selected.parent.parent;config=prefix/'pyvenv.cfg'
        # Only a known isolated venv makes absence of package files conclusive.
        try:isolated=config.is_file() and re.search(r'(?im)^include-system-site-packages\s*=\s*false\s*$',config.read_text()[:8000])
        except (OSError,UnicodeError):isolated=False
        workspace=Workspace(root);names=workspace.list_files();declared=False
        for name in ('pyproject.toml','requirements.txt','requirements-dev.txt'):
            if name not in names:continue
            try:
                content=workspace.text_bytes(name).decode()
                pattern=r'(?m)^\s*pytest(?:\[[^\]]+\])?(?:[<=>~!;\s]|$)' if name.startswith('requirements') else r'''(?ms)^\s*(?:dependencies|test|tests|dev)\s*=\s*\[[^\]]*["']pytest(?:[<=>~!\[;"'])'''
                declared=declared or bool(re.search(pattern,content))
            except (ValueError,OSError,UnicodeError):pass
        sites=list((prefix/'lib').glob('python*/site-packages'))+[prefix/'Lib/site-packages']
        installed=any((site/'pytest').exists() or (site/'pytest.py').exists() for site in sites)
        custom_paths=any(any(site.glob('*.pth')) for site in sites)
        project_module='pytest.py' in names or any(n.startswith('pytest/') for n in names)
        if isolated and declared and not installed and not project_module and not custom_paths:
            state.update(status='missing',missing='declared_pytest',evidence='The selected isolated environment has no pytest package, and the task copy declares pytest.',
                         next_step='Install the project-declared test dependencies in the task-copy environment, then re-check. No installation has been authorized by a test grant.')
    if state['status']=='missing':state['setup_commands'],state['sources']=guidance(task)
    return state
