"""Durable preparation of a reviewed candidate; never destination-write consent.

Git/model executors retain their existing authority and evidence checks. This
operation only owns their continuation, including page loss and process restart.
"""
import copy
import hashlib
import threading
import uuid
from pathlib import Path

from . import branch_workspace as work, branch_runs, branch_merge

LABELS = {'accepted':'Update request saved', 'checking':'Checking latest project',
          'combining':'Combining changes', 'resolving':'Resolving overlaps',
          'checks':'Running checks', 'review':'Independent review',
          'ready':'Ready for your review', 'waiting':'Waiting for local changes',
          'decision':'A decision is needed', 'failed':'Preparation needs attention', 'cancelled':'Preparation cancelled; saved work retained'}
TERMINAL = {'ready','decision','failed','cancelled'}


def candidate(task):
    run=task.get('branch_run')
    if run:return run.get('expected_feature_tip')
    return hashlib.sha256(task.get('patch','').encode()).hexdigest()


def _readiness(engine, task_id):
    task=engine.store.get(task_id);run=task.get('branch_run',{})
    source=run.get('workspace_mapping',{}).get('source') or task['source']
    target=run.get('target_ref') or task.get('integration_preparation',{}).get('target_ref') or work.source_git(source,'symbolic-ref','--quiet','HEAD')
    tip=work._tip(source,target)
    result={'code':'ready','actions':[], 'target_tip':tip,'target_ref':target,
            'candidate':candidate(task),'files':[], 'message':'Ready for review'}
    def blocked(code,message,actions=(),files=()):
        return {**result,'code':code,'message':message,'actions':list(actions),'files':list(files)}
    for owner in engine.admission.operations:
        if owner==task_id:continue
        other=engine.store.get(owner)
        other_source=other.get('branch_run',{}).get('workspace_mapping',{}).get('source') or other.get('source')
        if other_source==source:return blocked('integration_busy','Waiting for another task to finish integrating.')
    if not tip:return blocked('target_missing','The captured destination branch no longer exists.')
    destination=source
    if run:
        destination=branch_merge._destination(run['workspace_mapping'],target)
        branch_merge.destination_identity(run['workspace_mapping'],destination)
    result['destination']=destination
    dirty=None
    if destination:
        head=work.source_git(destination,'symbolic-ref','--quiet','HEAD')
        if head!=target:return blocked('destination_changed','The destination checkout is on a different branch.')
        markers=('MERGE_HEAD','CHERRY_PICK_HEAD','REVERT_HEAD','rebase-merge','rebase-apply','sequencer')
        for raw in work.source_git(destination,'rev-parse',*[arg for m in markers for arg in ('--git-path',m)]).splitlines():
            p=Path(raw)
            if (p if p.is_absolute() else Path(destination)/p).exists():
                return blocked('git_operation','An external Git operation is in progress. Finish it before integration.')
        raw=work.source_git(destination,'status','--porcelain=v1','-z','--untracked-files=all','--ignore-submodules=none',binary=True)
        if raw:
            files=branch_merge.local_paths(destination,raw)
            result['local_changes']=files
            dirty=blocked('dirty_destination','Waiting for local changes in the destination.',('inspect_local_changes',),files)
            # Branch preparation combines committed versions in the owned task
            # copy. Only overlapping destination edits block the eventual merge.
            # Interactive reconciliation still depends on the source snapshot.
            if not run:return dirty
    if run:
        try:engine.branch.validate_authority(task,run)
        except (ValueError,OSError) as error:return blocked('authority_changed',str(error))
        try:work.validate_owned(run['workspace_mapping'],run['expected_feature_tip'])
        except (ValueError,OSError) as error:return blocked('ownership_changed',str(error))
        if any(i.get('status') not in branch_runs.DONE for i in run.get('items',[])):
            return blocked('work_remaining','The current work must finish before integration.')
        inspect=('inspect_local_changes',) if dirty else ()
        try:work.source_git(source,'merge-base','--is-ancestor',tip,run['expected_feature_tip'])
        except ValueError:return blocked('target_advanced','The target changed while this task was running.',('update_resolve','keep_saved_work')+inspect)
        if not run.get('readiness'):return blocked('review_required','The combined candidate needs verification and review.',('update_resolve',)+inspect)
        if destination:
            overlaps=branch_merge.local_overlaps(destination,tip,run['expected_feature_tip'],result.get('local_changes',[]))
            if overlaps:
                return blocked('dirty_destination','Local edits overlap the reviewed changes. Both versions are preserved.',('inspect_local_changes',),overlaps)
        if dirty:
            result['message']='Ready for review. Unrelated local changes will be preserved.'
    else:
        from . import commits
        if not task.get('patch') and task.get('integration_preparation',{}).get('already_included'):
            from .engine import current_evidence
            check=(task.get('checks') or [{}])[-1];review=(task.get('checkpoints') or [{}])[-1]
            if current_evidence(task,check) and check.get('passed') and current_evidence(task,review) and review.get('decision')=='APPROVE' and review.get('diff')=='':
                return {**result,'already_included':True,'message':'Already included in the project; current checks and independent review passed.'}
            return blocked('review_required','Verify the already included work against the current project.',('update_resolve',))
        try:engine.reviewed_patch(task)
        except (ValueError,OSError) as error:return blocked('review_required',str(error))
        from . import git_workflow
        if git_workflow.enabled(task) and not task.get('follow_up'):
            captured=task.get('git_target',{})
            if captured and (captured.get('head')!=tip or captured.get('branch')!=target):
                return blocked('target_advanced','The project branch changed since this chat started.',('update_resolve','keep_saved_work'))
            baseline_entries=git_workflow._baseline_entries(task['workspace'],'HEAD')
            skipped=set(task.get('snapshot',{}).get('skipped',[]))
            expected={path:entry for path,entry in git_workflow._baseline_entries(source,tip).items() if path not in skipped}
            if baseline_entries!=expected:
                return blocked('target_advanced','The task baseline differs from the committed project.',('update_resolve','keep_saved_work'))
        baseline=task.get('reconciliation',{}).get('source_head') or task.get('integration_policy',{}).get('target_tip')
        if baseline and baseline!=tip:return blocked('target_advanced','The project changed since this task copy was captured.',('update_resolve','keep_saved_work'))
        try:commits.prepare(task)
        except commits.ProjectConflict as error:return blocked('text_conflicts',str(error),('update_resolve','keep_saved_work'),error.files)
        except (ValueError,OSError) as error:return blocked('precondition',str(error))
    return result


def readiness(engine,task_id):
    try:return _readiness(engine,task_id)
    except (ValueError,OSError) as error:
        task=engine.store.get(task_id)
        return {'code':getattr(error,'code','destination_unavailable'),'message':str(error),'actions':[],
                'files':getattr(error,'paths',[]),'candidate':candidate(task),'target_tip':None,'target_ref':task.get('branch_run',{}).get('target_ref') or task.get('integration_preparation',{}).get('target_ref')}


def _publish(engine,task,stage,status='running',**values):
    with engine.lock:
        current=engine.store.get(task['id']).get('integration_preparation',{})
        if current.get('id')!=task.get('integration_preparation',{}).get('id') or current.get('status')=='cancelled':
            task['integration_preparation']=copy.deepcopy(current)
            return False
        op=task['integration_preparation'];op.update(stage=stage,status=status,label=LABELS[stage],**values)
        if stage=='ready':
            op.pop('reason',None);op.pop('error',None)
        engine.store.save(task)
        return True


def _active(engine):
    if not hasattr(engine,'_integration_preparing'):engine._integration_preparing=set()
    return engine._integration_preparing


def _renew_unchanged_checks(engine,task):
    """The explicit update-and-recheck click covers the saved exact checks.

    Session grants expire on restart. Renew only commands whose approved runner,
    configuration and task-copy binding are still identical; never grant a wider
    project profile or carry this consent through background restore.
    """
    run=task.get('branch_run')
    if not run:return
    engine.branch.validate_authority(task,run)
    scopes=engine.branch.scopes
    for scope in run.get('check_scope',[]):
        if not scopes.authorize(task,scope['command'],directory=scope.get('check_directory','.')) and scopes.prepare(task,scope['command'],directory=scope.get('check_directory','.'))==scope:
            scopes.consent(task,scope,exact=True)


def _continued(engine,task_id,result,operation_id):
    """A background executor must retain an unmet permission, not drop it."""
    if not isinstance(result,dict):return
    if result.get('needs_consent'):
        reason={'code':'command_permission_required',
                'message':'The verification environment or session permissions changed. Review test permissions here to continue the saved update.',
                'commands':[scope['command'] for scope in result.get('scopes',[])]}
    elif result.get('needs_merge_recovery'):
        reason={'code':'merge_recovery_required','message':'Finish the already approved local integration before continuing.'}
    else:return
    with engine.lock:
        task=engine.store.get(task_id)
        if task.get('integration_preparation',{}).get('id')==operation_id and _permitted(engine,task) and not _running(engine,task_id):
            _publish(engine,task,'decision','decision',reason=reason)


def continuing(task):
    """Clear a fulfilled preparation prerequisite when the executor starts."""
    op=task.get('integration_preparation',{})
    if op.get('authorized') and op.get('status')=='decision' and op.get('reason',{}).get('code') in {'command_permission_required','merge_recovery_required'}:
        stage='resolving' if task.get('branch_run',{}).get('conflict_resolution') else 'checks'
        op.update(status='running',stage=stage,label=LABELS[stage])
        op.pop('reason',None)


def start(engine,task_id,values,*,renew_checks=True):
    allowed={'approved','target_tip','candidate','operation_id','target_ref','publication_id'}
    if set(values)-allowed or values.get('approved') is not True or not all(isinstance(values.get(k),str) and values[k] for k in ('target_tip','candidate')):
        raise ValueError('Approve preparation of the displayed target and candidate.')
    with engine.lock:
        engine.require_active_task(task_id)
        task=engine.store.get(task_id);saved=task.get('integration_preparation')
        if saved and saved.get('id')==values.get('operation_id') and (saved.get('requested_target_tip',saved.get('target_tip'))!=values['target_tip'] or saved.get('candidate')!=values['candidate'] or (values.get('target_ref') and saved.get('target_ref')!=values['target_ref']) or saved.get('publication_id')!=values.get('publication_id')):
            raise ValueError('That operation ID belongs to a different captured candidate or target.')
        retry_failed=bool(saved and saved.get('status') in {'failed','cancelled'} and values.get('operation_id') and values['operation_id']!=saved.get('id'))
        if saved and not retry_failed and (saved.get('id')==values.get('operation_id') or (saved.get('requested_target_tip',saved.get('target_tip'))==values['target_tip'] and saved.get('candidate')==values['candidate'] and (not values.get('target_ref') or saved.get('target_ref')==values['target_ref']) and saved.get('publication_id')==values.get('publication_id'))):
            if renew_checks and saved.get('authorized') and saved.get('status')=='decision' and saved.get('reason',{}).get('code')=='command_permission_required':
                engine.admission.require_idle(task_id)
                _renew_unchanged_checks(engine,task)
                continuing(task)
                engine.store.save(task)
            if saved.get('status') not in TERMINAL:_launch(engine,task_id)
            return copy.deepcopy(task)
        engine.admission.require_idle(task_id)
        if not task.get('branch_run') and not values.get('target_ref'):
            raise ValueError('Include the displayed target_ref when preparing an Interactive task.')
        if candidate(task)!=values['candidate']:raise ValueError('The saved candidate changed. Refresh Changes.')
        opid=values.get('operation_id') or uuid.uuid4().hex
        if not isinstance(opid,str) or len(opid)>100:raise ValueError('Invalid operation ID')
        if renew_checks:_renew_unchanged_checks(engine,task)
        if values.get('publication_id'):
            from .git_workflow import retire_publication
            retire_publication(engine,task,values)
        elif task.get('pull_request') and not task['pull_request'].get('url'):
            raise ValueError('Finish the saved publication or approve its destination recovery before updating this task.')
        if saved:task.setdefault('integration_preparation_history',[]).append(copy.deepcopy(saved))
        task['integration_preparation']={'id':opid,'candidate':values['candidate'],'target_tip':values['target_tip'],'requested_target_tip':values['target_tip'],
            'target_ref':values.get('target_ref') or task.get('branch_run',{}).get('target_ref') or task.get('integration_target_ref'),
            'status':'running','stage':'accepted','label':LABELS['accepted'],'authorized':True,
            **({'publication_id':values['publication_id']} if values.get('publication_id') else {}),
            'workspace_generation':task.get('workspace_generation',0),'workspace':task.get('workspace')}
        same_assignment=bool(saved and saved.get('candidate')==values['candidate']
            and saved.get('requested_target_tip',saved.get('target_tip'))==values['target_tip']
            and saved.get('target_ref')==task['integration_preparation']['target_ref']
            and saved.get('workspace')==task.get('workspace')
            and saved.get('workspace_generation',0)==task.get('workspace_generation',0))
        if retry_failed and same_assignment and saved.get('dispatched'):
            task['integration_preparation']['dispatched']=True
        engine.store.save(task)
        if values.get('publication_id'):
            getattr(engine,'pull_request_previews',{}).pop(task_id,None)
        receipt=copy.deepcopy(task)
        _launch(engine,task_id)
        return receipt


def _launch(engine,task_id):
    # This reservation is in-memory only; persisted stage is the restart source.
    if getattr(engine,'route_restore_stop',threading.Event()).is_set():return
    if task_id in _active(engine):return
    _active(engine).add(task_id)
    threading.Thread(target=_drive,args=(engine,task_id),daemon=True).start()


def _wait(engine,task,reason):
    _publish(engine,task,'waiting','waiting',reason=reason)
    timer=threading.Timer(15,lambda: resume(engine,task['id']))
    timer.daemon=True;timer.start()


def resume(engine,task_id):
    with engine.lock:
        task=engine.store.get(task_id);op=task.get('integration_preparation',{})
        if op.get('authorized') and op.get('status') not in TERMINAL:_launch(engine,task_id)


def _running(engine,task_id):
    rt=engine.runtimes.get(task_id)
    return bool(rt and rt.thread and rt.thread.is_alive())


def _drive(engine,task_id):
    try:
        task=engine.store.get(task_id);op=task['integration_preparation']
        if not op.get('authorized') or op.get('status') in TERMINAL:return
        if _running(engine,task_id):
            timer=threading.Timer(1,lambda: resume(engine,task_id));timer.daemon=True;timer.start();return
        run=task.get('branch_run')
        if run and run.get('target_update') and run['target_update'].get('origin')!='conflict_resolution':
            from . import branch_completion
            result=branch_completion.update_branch(engine.branch,task_id,{'approved':True,'update_token':branch_completion.update_token(run)})
            _continued(engine,task_id,result,op['id'])
            return
        # A saved assignment/reconciliation is resumed, never created twice.
        dispatched=op.get('dispatched') or (run and run.get('conflict_resolution',{}).get('preparation_id')==op['id'] and run.get('conflict_resolution',{}).get('status')!='integrated') or task.get('workspace_generation',0)>op['workspace_generation']
        if dispatched:
            if _finished(task):
                current=readiness(engine,task_id)
                if current['code']=='ready':_publish(engine,task,'ready','ready');return
                if current['code']=='target_advanced':
                    op.pop('dispatched',None);dispatched=False
                else:_wait(engine,task,current);return
            if dispatched:
                if not _permitted(engine,task):return
                mode='unattended' if run else 'interactive'
                if not engine.admission.snapshot()[mode]['allowed']:_wait(engine,task,'task_slot');return
                _publish(engine,task,'resolving' if (run and run.get('conflict_resolution')) or task.get('reconciliation',{}).get('conflicts') else 'checks')
                if run:_continued(engine,task_id,engine.branch.resume(task_id,{}),op['id'])
                else:_resume_interactive(engine,task)
                return
        _publish(engine,task,'checking')
        state=readiness(engine,task_id)
        if not _permitted(engine,task):return
        if state['code'] in {'dirty_destination','git_operation','integration_busy'}:_wait(engine,task,state);return
        if state['code'] not in {'ready','target_advanced','text_conflicts','review_required'}:
            _publish(engine,task,'decision','decision',reason=state);return
        if state['target_tip']!=op['target_tip']:
            # Only descendants of the explicitly displayed target are eligible.
            source=run['workspace_mapping']['source'] if run else task['source']
            try:work.source_git(source,'merge-base','--is-ancestor',op['target_tip'],state['target_tip'])
            except ValueError:
                _publish(engine,task,'decision','decision',reason={'code':'target_replaced','message':'The target history was replaced. Review the new destination.'});return
            op.setdefault('targets',[]).append(op['target_tip']);op['target_tip']=state['target_tip'];engine.store.save(task)
        mode='unattended' if run else 'interactive'
        if not engine.admission.snapshot()[mode]['allowed']:_wait(engine,task,'task_slot');return
        if not _publish(engine,task,'combining') or not _permitted(engine,task):return
        if run:
            from . import branch_completion,branch_conflicts
            if state['code'] in {'ready','review_required'}:
                op['dispatched']=True;engine.store.save(task)
                if state['code']=='ready':_publish(engine,task,'ready','ready')
                else:_continued(engine,task_id,engine.branch.resume(task_id,{}),op['id'])
            else:
                result=branch_completion.update_branch(engine.branch,task_id,{'approved':True,'update_token':branch_completion.update_token(run)})
                if isinstance(result,dict) and result.get('needs_conflict_resolution'):
                    task=engine.store.get(task_id);run=task['branch_run'];op=task['integration_preparation']
                    if not _publish(engine,task,'resolving') or not _permitted(engine,task):return
                    result=branch_conflicts.start(engine.branch,task_id,{'approved':True,'update_token':branch_completion.update_token(run)})
                _continued(engine,task_id,result,op['id'])
        else:
            engine.reconcile_project(task_id,{'patch_digest':candidate(task)})
            task=engine.store.get(task_id);op=task['integration_preparation']
            op['dispatched']=True;engine.store.save(task)
            # A redundant patch still needs evidence, never a synthetic merge.
            if not task.get('patch'):op['already_included']=True
            _publish(engine,task,'resolving' if task.get('reconciliation',{}).get('conflicts') else 'checks')
            _resume_interactive(engine,task)
    except Exception as error:
        with engine.lock:
            task=engine.store.get(task_id)
            _publish(engine,task,'failed','failed',reason={'code':getattr(error,'code','preparation_error'),'message':str(error),'files':getattr(error,'paths',[])})
    finally:
        with engine.lock:_active(engine).discard(task_id)


def _finished(task):
    run=task.get('branch_run')
    if run:
        # A completed review can pause solely because the target advanced. It
        # needs a fresh update, not another Resume of the old final review.
        reviewed=run.get('status')=='ready_for_merge' or (
            run.get('status')=='paused' and run.get('pause_reason')=='branch_drift')
        return run.get('status')=='merged' or (reviewed and bool(run.get('readiness'))
            and bool(run.get('items')) and all(i.get('status') in branch_runs.DONE for i in run['items']))
    return task.get('status') in {'approved','completed'} and not task.get('error')


def observe(engine,task):
    op=task.get('integration_preparation',{})
    if not op.get('authorized') or (op.get('status') in TERMINAL and op.get('status')!='decision'):return
    if op.get('status')=='decision' and task.get('status') in {'running','approved','completed'}:op['status']='running'
    if _finished(task):
        current=readiness(engine,task['id'])
        if current['code']=='ready':_publish(engine,task,'ready','ready');return
        if current['code']=='target_advanced':
            op.pop('dispatched',None);engine.store.save(task);resume(engine,task['id']);return
        _wait(engine,task,current);return
    if task.get('status')=='running':
        _publish(engine,task,'review' if task.get('active_role')=='reviewer' else 'resolving');return
    if task.get('status') in {'awaiting_reply','needs_input','needs_approval'}:
        _publish(engine,task,'decision','decision',reason={'code':'operator_decision','message':task.get('error') or 'Review the specific decision in this chat.'})
    elif task.get('status')=='paused' and task.get('branch_run',{}).get('pause_reason')=='branch_drift':
        op.pop('dispatched',None);engine.store.save(task);resume(engine,task['id'])
    elif task.get('status')=='paused':
        _publish(engine,task,'decision','decision',reason={'code':task.get('error_code'),'message':task.get('error') or 'Work is paused.'})


def restore(engine):
    for task in engine.store.list(fields=('id', 'integration_preparation')):
        operation = task.get('integration_preparation', {})
        if operation.get('authorized') and operation.get('status') not in TERMINAL:
            resume(engine,task['id'])


def local_changes(engine,task_id):
    state=readiness(engine,task_id)
    if 'destination' not in state:raise ValueError(state['message'])
    destination=state['destination']
    return {'diff':work.source_git(destination,'diff','HEAD','--no-ext-diff','--no-renames') if destination else '',
            'destination':destination, 'files':state.get('local_changes',state['files']), 'label':'Local changes in the destination checkout. This view is read-only.'}


def resolution_changes(engine,task_id):
    task=engine.store.get(task_id);run=task.get('branch_run',{});resolution=run.get('conflict_resolution',{})
    context=resolution.get('context',{})
    if not context:
        if task.get('reconciliation'):return _interactive_resolution_changes(task)
        return {'diff':'','files':[], 'label':'No captured conflict resolution'}
    source=run['workspace_mapping']['source']
    current=run['expected_feature_tip']
    return {'diff':work.source_git(source,'diff','--no-ext-diff','--no-renames',context['old_tip'],current),
            'base':context['old_tip'],'candidate':current,'target_tip':context['target_tip'],
            'files':context['conflicts'],'label':'Task before update → current combined candidate',
            'summary':next((i.get('outcome_summary','') for i in run.get('items',[]) if i['id']==resolution.get('item_id')),'')}


def automatic(engine,task):
    """Called near completion only; old tasks without captured authority stay put."""
    policy=task.get('integration_policy',{})
    if policy.get('keep_up_to_date') is not True:return False
    if _running(engine,task['id']):
        if not getattr(engine,'route_restore_stop',threading.Event()).is_set():
            timer=threading.Timer(1,lambda: automatic(engine,engine.store.get(task['id'])));timer.daemon=True;timer.start()
        return True
    run=task.get('branch_run')
    if run:
        saved=run.get('authorization',{}).get('contract',{}).get('integration_policy',{})
        if saved!=policy:return False
    existing=task.get('integration_preparation')
    if existing and existing.get('status')=='cancelled':return False
    if existing and existing.get('status') not in TERMINAL:
        resume(engine,task['id']);return True
    current=readiness(engine,task['id'])
    if current['code'] not in {'target_advanced','text_conflicts'}:return False
    source=run['workspace_mapping']['source'] if run else task['source']
    authorized_target=policy.get('target_tip')
    if not authorized_target or policy.get('target_ref')!=current['target_ref']:return False
    try:work.source_git(source,'merge-base','--is-ancestor',authorized_target,current['target_tip'])
    except ValueError:return False
    start(engine,task['id'],{'approved':True,'target_tip':current['target_tip'],'candidate':current['candidate'],'target_ref':current['target_ref']},renew_checks=False)
    return True


def _resume_interactive(engine,task):
    if not _permitted(engine,task):return
    if not task.get('patch') and task['integration_preparation'].get('already_included'):
        # Reconciliation found the requested patch already present. Verify the
        # new environment and original criteria; no synthetic approval/commit.
        task.update(status='paused',error=None,error_code=None,finish_review=True,active_role='worker')
        task['pending_checkpoint']={'summary':'Verify the original request against the current project; the saved edits are already included.',
                                    'uncertainties':'Check original acceptance criteria and preservation of incoming behavior with current evidence.'}
        engine.store.save(task)
    engine.start(task['id'])


def _permitted(engine,task):
    current=engine.store.get(task['id']).get('integration_preparation',{})
    return bool(current.get('authorized') and current.get('id')==task.get('integration_preparation',{}).get('id') and current.get('status')!='cancelled')


def cancel(engine,task_id):
    """Withdraw preparation dispatch, never discard candidate/files/evidence."""
    with engine.lock:
        task=engine.store.get(task_id)
        op=task.setdefault('integration_preparation',{'id':uuid.uuid4().hex})
        if op:
            op.update(status='cancelled',stage='cancelled',label=LABELS['cancelled'],authorized=False)
            engine.store.save(task)
            runtime=engine.runtimes.get(task_id)
            if runtime and runtime.task.get('integration_preparation',{}).get('id')==op['id']:
                runtime.task['integration_preparation']=copy.deepcopy(op)
        return task


def _interactive_resolution_changes(task):
    """Compare retained isolated copies; never read arbitrary destination paths."""
    import difflib
    from .workspace import Workspace
    info=task['reconciliation']
    previous=Workspace(info['previous_workspace']);current=Workspace(task['workspace'])
    chunks=[]
    for name in sorted(set(info.get('files',[]))):
        versions=[]
        for workspace in (previous,current):
            path=workspace.path(name)
            versions.append(workspace.text_bytes(name).decode('utf-8').splitlines(keepends=True) if path.exists() else [])
        chunks.extend(difflib.unified_diff(*versions,fromfile='before-update/'+name,tofile='current-candidate/'+name))
    diff=''.join(chunks)
    return {'diff':diff,'files':info.get('conflicts',[]),'target_tip':info['source_head'],
            'base':work.source_git(str(previous.root),'rev-parse','HEAD'),
            'candidate':candidate(task),'comparison_id':hashlib.sha256(diff.encode()).hexdigest(),
            'label':'Previous saved task copy → current task copy (including uncommitted edits)',
            'summary':'Combined with project revision '+info['source_head'][:12]+'. The retained comparison supplements the final changes against the project.'}
