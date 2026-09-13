"""Two-phase observer driver. Prepare has no inference; Start requires reviewed digest."""
import argparse
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from exporter_live import save, git, fingerprint, runtime_hash, accounting

PROFILE_FILES = ('config.json', 'preferences.json', 'gateway.json')


def fixture(app):
    spec = importlib.util.spec_from_file_location('routing_matrix_fixture', app/'docs/trials/matrix/run_live.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.fixture('easy')


def safe_result(task):
    requests = task.get('request_metrics', [])
    events = []
    scopes = {}
    for request in requests:
        scope = request.get('dispatch_scope')
        if isinstance(scope,dict) and all(isinstance(scope.get(k),str) for k in ('base_url','connection_revision','model','role')):
            identity = hashlib.sha256(json.dumps({k:scope[k] for k in ('base_url','connection_revision','model','role')},sort_keys=True,separators=(',',':')).encode()).hexdigest()
            scopes[identity] = {'scope_hash':identity,'model':scope['model'],'role':scope['role'],
                                'access_class':request.get('access_class') if request.get('access_class') in ('included','public_free') else 'unknown'}
    for event in task.get('events', []):
        if event.get('kind') not in {'routing', 'handoff', 'worker_recovery'}: continue
        detail = event.get('detail') or {}
        events.append({'kind': event['kind'], 'title': event.get('title', '')[:160],
                       'detail': {k: detail[k] for k in ('model','role','from','to','attempt','scope','tool_check','completed','independently_disproved')
                                  if k in detail and isinstance(detail[k], (str,int,bool))}})
    return {'status': task.get('branch_run', {}).get('status'),
            'models': {r: sorted({q['model'] for q in requests if q.get('role')==r and isinstance(q.get('model'),str)})
                       for r in ('worker','reviewer')},
            'request_count': sum(q.get('dispatched') is True for q in requests),
            'accounting': accounting(task), 'route_events': events, 'dispatch_scopes': sorted(scopes.values(),key=lambda s:s['scope_hash']),
            'routing_traces': task.get('routing_traces', []),
            'request_metrics': [{k:q[k] for k in ('id','role','model','purpose','status','dispatched','seconds',
                'input_tokens','output_tokens','cost_provenance','served_model','identity_provenance','failure_category') if k in q} for q in requests]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    phase=parser.add_mutually_exclusive_group(required=True)
    phase.add_argument('--prepare',action='store_true');phase.add_argument('--start',action='store_true')
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--app-repo',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--config-dir',type=Path)
    parser.add_argument('--reviewed-digest')
    args=parser.parse_args();app=args.app_repo.resolve(strict=True);root=args.root.resolve()
    if root==app or app in root.parents:parser.error('Trial root must be outside app source')
    sys.path.insert(0,str(app))
    from cheapos.engine import Engine
    from cheapos.branch_authorization import digest
    from cheapos import branch_completion
    source=root/'project';state=root/'state';engine=None;task=None
    result={'phase':'prepare' if args.prepare else 'start','operator_prepared_plan':True,'interventions_after_start':0}
    if args.prepare:
        if not args.config_dir:parser.error('--config-dir required')
        if git(app,'status','--porcelain'):parser.error('Commit app changes first')
        root.mkdir(mode=0o700);source.mkdir();state.mkdir(mode=0o700)
        for name in PROFILE_FILES:save(state/name,json.loads((args.config_dir/name).read_text()))
        files,items=fixture(app)
        for name,content in files.items():(source/name).write_text(content)
        git(source,'init','-qb','main');git(source,'config','user.name','cheapoS Routing Trial');git(source,'config','user.email','trial@example.invalid')
        git(source,'add','.');git(source,'commit','-qm','Independent easy acceptance baseline')
        command='python3 -B -m unittest -v test_acceptance'
        identity,title,instructions,criteria=items[0]
        plan={'measurement':True,'limits':{'dollars':0},'items':[{'id':identity,'title':title,'instructions':instructions,
              'acceptance_criteria':criteria,'dependencies':[],'required_checks':[command]}],'final_checks':[command]}
        frozen={'app_sha':git(app,'rev-parse','HEAD'),'runtime_hash':runtime_hash(app),
                'source_sha':git(source,'rev-parse','HEAD'),'fixture':fingerprint(source,list(files)),
                'tests':fingerprint(source,['test_acceptance.py']), 'access_config':fingerprint(state,list(PROFILE_FILES)), 'plan':plan}
        save(root/'baseline.private.json',frozen)
    else:
        if not args.reviewed_digest:parser.error('--reviewed-digest required; inspect proposal first')
        frozen=json.loads((root/'baseline.private.json').read_text())
        if git(app,'rev-parse','HEAD')!=frozen['app_sha'] or runtime_hash(app)!=frozen['runtime_hash']:parser.error('App changed; prepare fresh attempt')
        if git(app,'status','--porcelain'):parser.error('App must remain clean')
        if fingerprint(state,list(PROFILE_FILES))!=frozen['access_config']:parser.error('Access/config changed')
        if git(source,'rev-parse','main')!=frozen['source_sha'] or git(source,'status','--porcelain'):parser.error('Source changed')
    result.update(app_sha=frozen['app_sha'], runtime_hash=frozen['runtime_hash'],
                  fixture_hash=frozen['fixture']['sha256'], tests_hash=frozen['tests']['sha256'],
                  access_config_hash=frozen['access_config']['sha256'])
    started=time.monotonic()
    try:
        marker=root/('prepare.intent' if args.prepare else 'start.intent')
        fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
        engine=Engine(state)
        if args.prepare:
            # prepare snapshots and consent scopes; never plans through a model.
            proposal=engine.branch.prepare({'repository':str(source),'prompt':'Complete the exact easy qualification. No merge or push.',
                'base_ref':'refs/heads/main','target_ref':'refs/heads/main','feature_ref':'refs/heads/feature/routing-trial','plan':frozen['plan']})
            task=engine.store.get(proposal['task_id'])
            save(root/'proposal.private.json',proposal)
        else:
            proposal=json.loads((root/'proposal.private.json').read_text());task=engine.store.get(proposal['task_id'])
        if task.get('execution',{}).get('mode')!='remote' or not task.get('route'):
            raise ValueError('Require automatic remote execution; no pinned/local/delegate fallback')
        if task['branch_run']['plan'].get('measurement') is not True or task['branch_run']['limits']['dollars']!=0:
            raise ValueError('Require measurement and zero paid spend')
        if args.prepare:
            if task.get('request_metrics'):raise ValueError('Prepare unexpectedly recorded inference')
            result.update(task_id=task['id'],proposal_digest=proposal['digest'],status='awaiting_inspection')
        else:
            fresh=engine.branch.proposal(task['id'])
            if proposal['digest']!=args.reviewed_digest or digest(proposal['contract'])!=args.reviewed_digest or fresh['contract']!=proposal['contract'] or fresh['digest']!=args.reviewed_digest:
                raise ValueError('Fresh proposal differs from reviewed contract')
            save(root/'start-proposal.private.json',fresh)
            engine.branch.authorize(task['id'],{'proposal_id':fresh['proposal_id'],'approved':True})
            runtime=engine.runtimes[task['id']]
            while runtime.thread.is_alive():runtime.thread.join(5)
            task=engine.store.get(task['id']);result.update(safe_result(task))
            receipts=[];run=task['branch_run'];parent=frozen['source_sha']
            for item in run['items']:
                receipt=item.get('commit_receipt') or {}
                if receipt.get('stage')=='completed' and receipt.get('run_id')==run['id'] and receipt.get('item_id')==item['id']:
                    sha=receipt['new_tip'];actual_parent=git(source,'rev-parse',sha+'^')
                    receipts.append({'item_id':item['id'],'sha':sha,'tree':git(source,'rev-parse',sha+'^{tree}'),
                                     'parent':actual_parent,'parent_matches':actual_parent==parent,
                                     'is_commit':git(source,'cat-file','-t',sha)=='commit'})
                    parent=sha
            result['completed_receipts']=receipts
            result['merge_available']=False
            if run['status']=='ready_for_merge':
                result['merge_available']=branch_completion.preview(engine.branch,task['id'])['merge_available']
            result['checks']=[{k:c.get(k) for k in ('command','passed','outcome','duration')} for c in task.get('checks',[])]
    except BaseException as error:
        result['error_type']=type(error).__name__
        save(root/'error.private.json',{'type':type(error).__name__,'detail':str(error)})
    finally:
        if engine:
            if any(r.thread and r.thread.is_alive() for r in engine.runtimes.values()):result['interventions_after_start']+=1
            engine.shutdown()
            if task:
                task=engine.store.get(task['id']);save(root/'task.private.json',task)
                if args.start:result.update(safe_result(task))
        result.update(elapsed_seconds=time.monotonic()-started,app_unchanged=runtime_hash(app)==frozen['runtime_hash'],
                      source_main_unchanged=git(source,'rev-parse','main')==frozen['source_sha'],source_clean=not bool(git(source,'status','--porcelain')),
                      source_tests_unchanged=fingerprint(source,['test_acceptance.py'])==frozen['tests'],
                      access_config_unchanged=fingerprint(state,list(PROFILE_FILES))==frozen['access_config'])
        if task and task.get('workspace'):
            result['candidate_tests_unchanged']=fingerprint(Path(task['workspace']),['test_acceptance.py'])==frozen['tests']
        result['qualified']=bool(args.start and not result.get('error_type') and result.get('status')=='ready_for_merge'
            and result.get('merge_available') and len(result.get('completed_receipts',[]))==1
            and all(r['is_commit'] and r['parent_matches'] for r in result.get('completed_receipts',[]))
            and all(result.get(k) for k in ('app_unchanged','source_main_unchanged','source_clean','source_tests_unchanged','candidate_tests_unchanged')))
        save(root/('prepare-result.json' if args.prepare else 'result.json'),result);print(json.dumps(result,sort_keys=True))
    return 1 if result.get('error_type') else 0


if __name__=='__main__':raise SystemExit(main())
