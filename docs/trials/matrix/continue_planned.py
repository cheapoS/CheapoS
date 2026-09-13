"""Execute one explicitly inspected live-planning proposal without replanning.

Requires --live, the existing planning --root, and its --reviewed-digest. This
refreshes only the ephemeral proposal token, compares the entire saved contract,
then starts once. It never resumes, approves extra commands, revises, or merges.
Private state stays in the original external trial directory. Shareable execution
results omit prompts, endpoints, credentials, model output, and check output.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time

from plan_live import REPO, code_hash, numeric, private_json
from cheapos.engine import Engine
from cheapos.workspace import git
from cheapos.branch_authorization import digest
from cheapos import branch_completion, metrics


def delta(after, before):
    if isinstance(after, dict):
        before = before if isinstance(before, dict) else {}
        return {key: delta(value, before.get(key, {} if isinstance(value, dict) else 0)) for key, value in after.items()}
    return after - before


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Existing planning-LEVEL-INPUT-ATTEMPT directory')
    parser.add_argument('--reviewed-digest', required=True, help='Exact proposal digest already inspected by the operator')
    parser.add_argument('--live', action='store_true', help='Authorize execution of this inspected proposal')
    args = parser.parse_args()
    if not args.live:
        parser.error('Starting the inspected proposal requires explicit --live')
    if not re.fullmatch('[0-9a-f]{64}', args.reviewed_digest):
        parser.error('Use the complete SHA-256 digest of the inspected proposal')
    root = args.root.expanduser().resolve(strict=True)
    if root == REPO or REPO in root.parents:
        parser.error('Trial state must be outside the repository')
    if (root / 'execution-result.json').exists() or (root / 'execution-start.private.json').exists():
        parser.error('This execution attempt is already recorded; this driver cannot silently retry or resume it')
    saved = json.loads((root / 'proposal.private.json').read_text())
    planning = json.loads((root / 'result.json').read_text())
    if planning.get('status') != 'proposal':
        parser.error('The planning attempt did not produce a proposal')
    if saved.get('digest') != args.reviewed_digest or planning.get('proposal_digest') != args.reviewed_digest or digest(saved['contract']) != args.reviewed_digest:
        parser.error('The saved proposal differs from the inspected digest')
    if planning.get('app_code_hash') != code_hash():
        parser.error('Application code changed since planning; qualify a fresh planning attempt explicitly')
    try:
        lease=os.open(str(root / '.execution-driver.lock'),os.O_WRONLY | os.O_CREAT | os.O_EXCL,0o600)
    except FileExistsError:
        parser.error('Another continuation attempt already claimed this planning root')
    with os.fdopen(lease,'w') as stream:stream.write(str(os.getpid())+'\n')
    source = root / 'project'; task_id = saved['task_id']; app_before = code_hash()
    baseline = saved['contract']['base_sha']
    tests_before = hashlib.sha256((source / 'test_acceptance.py').read_bytes()).hexdigest()
    started = time.monotonic(); engine = None; task = None; authorized = False
    usage_before = {}; consumption_before = {}; request_ids_before = set(); planning_metrics = None
    result = {'kind':'planned_input_execution', 'level':planning.get('level'), 'attempt':planning.get('attempt'),
              'input':planning.get('input'), 'profile_name':planning.get('profile_name'), 'run_id':task_id,
              'app_commit':git(REPO,'rev-parse','HEAD').strip(), 'app_code_hash':app_before,
              'reviewed_digest':args.reviewed_digest, 'planning_seconds':planning.get('planning_seconds'),
              'operator_prepared_plan':False, 'replanned':False, 'interventions_after_start':0,
              'intervention_reasons':[], 'status':'not_started'}
    try:
        engine = Engine(root / 'state')
        task = engine.store.get(task_id)
        usage_before = numeric(task.get('usage', {})); consumption_before = numeric(task['branch_run']['consumption'])
        planning_metrics = metrics.aggregate(task)
        request_ids_before = {q['id'] for q in task.get('request_metrics', []) if q.get('id')}
        refreshed = engine.branch.proposal(task_id)
        if refreshed['task_id'] != task_id or refreshed['digest'] != args.reviewed_digest or refreshed['contract'] != saved['contract']:
            raise ValueError('Refreshed proposal changed; inspect a new proposal before authorizing')
        if engine.store.get(task_id)['usage'] != task['usage']:
            raise ValueError('Read-only proposal refresh unexpectedly changed usage')
        private_json(root / 'refreshed-proposal.private.json', refreshed)
        # Exclusive intent marker makes an uncertain Start a recorded attempt.
        fd = os.open(str(root / 'execution-start.private.json'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump({'task_id':task_id, 'reviewed_digest':args.reviewed_digest}, stream)
        engine.branch.authorize(task_id, {'proposal_id':refreshed['proposal_id'], 'approved':True})
        authorized = True
        runtime = engine.runtimes.get(task_id)
        previous = None
        while runtime and runtime.thread.is_alive():
            runtime.thread.join(5)
            current = engine.store.get(task_id)
            snapshot = (current['status'], current['worker_turns'], len(current['checks']), len(current.get('request_metrics',[])), bool(current.get('pending_approval')))
            if snapshot != previous:
                print(json.dumps({'status':snapshot[0], 'worker_turns':snapshot[1], 'checks':snapshot[2],
                                  'retained_requests':snapshot[3], 'waiting_for_command_approval':snapshot[4]}), flush=True)
                previous = snapshot
    except KeyboardInterrupt:
        result['interventions_after_start'] += int(authorized)
        result['intervention_reasons'].append('operator_keyboard_interrupt')
        result['error_type'] = 'KeyboardInterrupt'
    except Exception as error:
        result['error_type'] = type(error).__name__
        private_json(root / 'execution-error.private.json', {'type':type(error).__name__, 'detail':str(error)})
    finally:
        if engine:
            active=any(rt.thread and rt.thread.is_alive() for rt in engine.runtimes.values())
            if active and 'error_type' in result and result['error_type']!='KeyboardInterrupt':
                result['interventions_after_start']+=1
                result['intervention_reasons'].append('driver_error_stopped_active_run')
            # Normal runs have already stopped. Explicit interruption is recorded
            # above rather than represented as autonomous completion.
            engine.shutdown()
            task = engine.store.get(task_id)
        result['driver_seconds'] = time.monotonic() - started
        result['start_authorized'] = bool(task and task.get('branch_run',{}).get('authorization'))
        if result.get('error_type')=='KeyboardInterrupt' and result['start_authorized']:
            result['interventions_after_start']=max(1,result['interventions_after_start'])
        if task:
            run = task['branch_run']; records = task.get('request_metrics', [])
            execution_records = [q for q in records if q.get('id') not in request_ids_before]
            usage_after = numeric(task.get('usage',{})); consumption_after = numeric(run['consumption'])
            independent = {'app_code_unchanged':app_before == code_hash(),
                           'source_main_unchanged':git(source,'rev-parse','main').strip() == baseline,
                           'source_clean':not git(source,'status','--porcelain'),
                           'source_tests_unchanged':hashlib.sha256((source/'test_acceptance.py').read_bytes()).hexdigest() == tests_before,
                           'tests_unchanged':hashlib.sha256((Path(task['workspace'])/'test_acceptance.py').read_bytes()).hexdigest() == tests_before}
            if run['status'] == 'ready_for_merge':
                preview = branch_completion.preview(engine.branch, task_id)
                independent['merge_available'] = preview['merge_available']
                independent['commits_verified'] = all(item.get('commit_receipt',{}).get('stage') == 'completed'
                    and item['commit_receipt']['run_id'] == task_id and item['commit_receipt']['item_id'] == item['id']
                    and git(source,'cat-file','-t',item['commit_receipt']['new_tip']).strip() == 'commit' for item in run['items'])
            result.update(status=run['status'], error_code=task.get('error_code'), measurement=run['plan'].get('measurement'),
                          planning_usage=usage_before, execution_usage_delta=delta(usage_after,usage_before), cumulative_usage=usage_after,
                          planning_consumption=consumption_before, execution_consumption_delta=delta(consumption_after,consumption_before),
                          cumulative_consumption=consumption_after, planning_metrics=planning_metrics, cumulative_metrics=metrics.aggregate(task),
                          models={role:config.get('model') if config else None for role,config in task['providers'].items()},
                          execution_models_used={role:sorted({q['model'] for q in execution_records if q.get('role')==role and q.get('model')}) for role in ('worker','reviewer')},
                          retained_execution_request_count=len(execution_records), request_history_truncated=bool(task.get('request_metrics_truncated')),
                          execution_request_count=consumption_after.get('requests',0)-consumption_before.get('requests',0),
                          handoffs=sum(event['kind']=='handoff' and event['title'].startswith('Switching') for event in task['events']),
                          review_revisions=sum(event['kind']=='review' and isinstance(event.get('detail'),dict) and event['detail'].get('decision')=='REQUEST_CHANGES' for event in task['events']),
                          checks=[{key:check.get(key) for key in ('passed','duration','allowed_seconds','outcome')} for check in task['checks']],
                          commits=[item['commit_receipt']['new_tip'] for item in run['items'] if item.get('commit_receipt')], independent=independent)
            result['autonomous_execution_success'] = authorized and 'error_type' not in result and run['status']=='ready_for_merge' and result['interventions_after_start']==0 and all(independent.values())
            # Full task diagnostics remain private. Never place raw model/check
            # output or configuration in the shareable execution result.
            if task.get('error'):
                private_json(root / 'execution-task-error.private.json', {'error':task['error']})
        private_json(root / 'execution-result.json', result)
        print(json.dumps({'status':result['status'], 'result':str(root/'execution-result.json'),
                          'autonomous_execution_success':result.get('autonomous_execution_success',False)}), flush=True)
    return 0 if result.get('autonomous_execution_success') else 1


if __name__ == '__main__':
    raise SystemExit(main())
