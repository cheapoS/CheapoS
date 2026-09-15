"""Explicit full-suite consent; model-selected commands cannot grant it."""
import shlex
from pathlib import PurePath


def argv(command):
    return shlex.split(command) if isinstance(command, str) else list(command)


def full_suite(command):
    args = argv(command)
    names = [PurePath(a).name for a in args]
    if 'check.py' in names:
        return '--full' in args
    if 'dev_tests.py' in names:
        return (not any(a in args for a in ('--pattern', '--suite')) and not any(a.startswith(('--pattern=','--suite=')) for a in args)) or '--suite=full' in args or any(args[i:i+2] == ['--suite','full'] for i in range(len(args)))
    if 'unittest' in args:
        rest = args[args.index('unittest')+1:]
        if 'discover' not in rest:
            return not any(not a.startswith('-') for a in rest)
        # A specific filename pattern/module directory is scoped. Default discovery is broad.
        for i,a in enumerate(rest):
            if a in ('-p','--pattern') and i+1<len(rest):
                return rest[i+1] in ('test*.py','test_*.py','*.py','*')
            if a.startswith('--pattern='):
                return a.split('=',1)[1] in ('test*.py','test_*.py','*.py','*')
        return True
    if 'pytest' in names or 'pytest' in args:
        rest=args[(names.index('pytest') if 'pytest' in names else args.index('pytest'))+1:]
        return not any('.py' in a or '::' in a or a in ('-k','-m') for a in rest)
    return False


def plan_commands(plan):
    commands=[c for i in plan.get('items',[]) for c in i.get('required_checks',[])]+plan.get('final_checks',[])
    return list(dict.fromkeys(shlex.join(argv(c)) for c in commands if full_suite(c)))


def disclosure(engine, task):
    commands=plan_commands(task['branch_run']['plan'])
    samples=[]
    for saved in getattr(engine.store,'tasks',{}).values():
        if saved.get('source') != task.get('source'):continue
        records=saved.get('checks',[])+[{**e['detail'],'time':e.get('time','')} for e in saved.get('events',[]) if e.get('kind')=='checks' and isinstance(e.get('detail'),dict)]
        samples.extend(c for c in records if c.get('duration') is not None and shlex.join(argv(c.get('command',[]))) in commands)
    latest=max(samples,key=lambda c:c.get('time',''),default={})
    return {'full_suite_checks':commands,'full_suite_last_seconds':latest.get('duration')}


def approve(task, approved):
    commands=plan_commands(task['branch_run']['plan'])
    if commands and approved is not True:
        raise ValueError('Full-suite validation needs explicit approval in Review & start. Choose focused checks or acknowledge the full-suite cost.')
    task['full_suite_approval']=commands
    task['branch_run']['test_policy_version']=1


def require_verification(command):
    args = argv(command)
    if 'check.py' in [PurePath(a).name for a in args] and '--plan' in args:
        raise ValueError('check.py --plan lists checks but runs none. Inspect its suggested commands, then call run_checks with the relevant executable check command. Do not substitute the full suite.')


def guard(task, command):
    require_verification(command)
    if not task.get('branch_run') or not full_suite(command):return
    canonical=shlex.join(argv(command))
    if canonical in task.get('full_suite_approval',[]):return
    run=task['branch_run']
    # Preserve already-authorized live/legacy runs, only for their captured commands.
    if not run.get('test_policy_version') and run.get('authorization_ref') and canonical in plan_commands(run.get('plan',{})):return
    raise ValueError('Full-suite command was not explicitly approved. Use focused checks from repository guidance, or ask the operator to revise and approve the check requirements in recovery controls.')
