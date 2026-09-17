"""Read-only setup checks for an inspected unattended proposal; grants nothing."""
import os
import shlex
from pathlib import Path
from . import environment
from .instructions import DEFAULT_CATALOG

POLICY = DEFAULT_CATALOG.get("workflow.unattended_setup_policy").text


def inspect(task, scopes):
    checks=[]
    root=Path(task['workspace'])
    usable=root.is_dir() and os.access(root,os.R_OK|os.W_OK|os.X_OK)
    checks.append({'id':'workspace','label':'Private working directory','status':'ready' if usable else 'blocked',
                   'detail':'Start covers reading and editing this task copy.' if usable else 'The private task directory is unavailable or not writable.'})
    for index,scope in enumerate(scopes):
        argv=scope['command']
        try:
            found=environment.inspect(task,argv)
            ready=found['status']=='ready'
            detail=('Start authorizes this command'+(' and its displayed test profile.' if scope.get('profile') else ' exactly.')
                    +' Observable prerequisites are present; undeclared dependencies and future environment changes remain unverified.') if ready else found['evidence']+' '+found['next_step']
        except (OSError,ValueError) as error:
            ready=False;detail='Could not inspect this command environment: '+str(error)[:500]
        checks.append({'id':'command-'+str(index),'label':shlex.join(argv),'status':'ready' if ready else 'blocked','detail':detail})
    assumptions=task.get('planning_assumptions',[])
    return {'ready':bool(scopes) and all(c['status']=='ready' for c in checks),'checks':checks,
            'assumptions':[a for a in assumptions if isinstance(a,str)][:12], 'policy':POLICY}


def require_ready(task, scopes):
    result=inspect(task,scopes)
    if not result['ready']:
        raise ValueError('Unattended setup needs attention before Start: '+'; '.join(c['detail'] for c in result['checks'] if c['status']=='blocked'))
    return result

WORKER_POLICY = DEFAULT_CATALOG.get("workflow.unattended_policy").text


def reconsider_question(task, question):
    run=task.get('branch_run',{})
    if 'continue_independent' not in run.get('plan',{}) or not run.get('authorization_ref'):return False
    item=next((i for i in run.get('items',[]) if i['id']==run.get('current_item_id')),None)
    if item is None or item.get('clarification_rechecked'):return False
    item['clarification_rechecked']=True
    item['clarification_candidate']=question[:2000]
    return True
