"""Independent item review, using actual checks and captured acceptance criteria."""
import copy
import json
import shlex

from . import branch_evidence as evidence
from . import branch_runs


def context(run, item):
    return dict(run_id=run['id'], plan_revision=run['plan_revision'], plan_digest=run['plan_digest'],
                item_id=item['id'], item_revision=item.get('revision', 1), feature_parent=run['expected_feature_tip'])


def checkpoint(engine, runtime, args):
    from .engine import REVIEW_TOOLS, REVIEW_SYSTEM, ProgressPause
    task = runtime.task
    run = branch_runs.require_supported(task['branch_run'])
    item = next(i for i in run['items'] if i['id'] == run['current_item_id'])
    if not item['required_checks']:
        raise ProgressPause('This item has no agreed verification command. Update the run proposal before continuing.')
    if task['active_role'] == 'reviewer':
        raise ProgressPause('Takeover implementation needs a different independent reviewer before a branch commit.')
    ctx = context(run, item)
    specs, criteria = item['required_checks'], item['acceptance_criteria']
    if item['status']=='reviewing': branch_runs.transition_item(run,item['id'],'working')
    branch_runs.transition_item(run, item['id'], 'checking')
    current = evidence.candidate(task, ctx, specs, criteria)
    for expected in current['checks']:
        try:
            record = next((c for c in reversed(task['checks']) if c['command'] == expected['command']), {})
            evidence.bind_check(current, expected['command'], record)
            engine.event(task, 'check_reused', 'Reusing current item verification', {'command':expected['command']})
        except ValueError:
            result = engine.checks(runtime, shlex.join(expected['command']))
            if not result['passed']:
                branch_runs.transition_item(run, item['id'], 'working')
                return {'decision':'REQUEST_CHANGES', 'feedback':'Repair the failing required check.', 'checks':result}
    current = evidence.candidate(task, ctx, specs, criteria)
    checks = evidence.current_checks(current, task['checks'])
    packet = evidence.review_packet(current, item, run['plan'], checks, str(args.get('uncertainties', ''))[:2000])
    if len(json.dumps(packet)) > 30000:
        raise ProgressPause('Item review exceeds 30,000 characters. Split the item in a revised proposal; no evidence was omitted.')
    branch_runs.transition_item(run, item['id'], 'reviewing')
    tools = copy.deepcopy(REVIEW_TOOLS)
    decision = next(t for t in tools if t['function']['name'] == 'review_decision')['function']['parameters']
    decision['properties'].update(candidate_id={'type':'string'}, criteria_outcomes={'type':'object', 'description':'Map every exact acceptance criterion to {passed:boolean,evidence:string}.'})
    decision['required'] += ['candidate_id','criteria_outcomes']
    messages = [{'role':'system','content':REVIEW_SYSTEM+' This is an Unattended item. Return the exact candidate_id and evidence for every acceptance criterion. APPROVE requires the whole item, not only a partial checkpoint.'}, {'role':'user','content':json.dumps(packet)}]
    if task.get('pending_review',{}).get('branch_candidate_id')!=current['id']:
        task['pending_review']={'branch_candidate_id':current['id'],'review_requests':0}
    task['status'] = 'reviewing'
    engine.event(task, 'checkpoint', 'Reviewing the complete branch item', {'item_id':item['id'], 'candidate_id':current['id']})
    for _ in range(8):
        runtime.guard()
        message = engine.request(runtime, messages, tools, 'reviewer')
        task['review_count'] += 1
        messages.append(message)
        calls = message.get('tool_calls', [])
        if len(calls) > 8:
            raise ProgressPause('Reviewer exceeded the bounded tool-call allowance.')
        if not calls:
            messages.append({'role':'user','content':'Call review_decision with the candidate ID and every criterion outcome.'})
        for call in calls:
            if runtime.stop.is_set(): raise InterruptedError('Task stopped')
            name, params = engine.parse_call(call)
            if name == 'review_decision':
                choice = params.get('decision')
                if choice == 'APPROVE':
                    try:
                        receipt = evidence.ready_receipt(current, checks, params, task['providers']['worker'], task['providers']['reviewer'], params.get('criteria_outcomes'))
                        evidence.revalidate(receipt, task, ctx, specs, criteria)
                    except ValueError as error:
                        result = {'error':str(error)}
                    else:
                        task.pop('pending_review',None)
                        item['ready_receipt'] = receipt
                        item['outcome_summary'] = str(params.get('feedback',''))[:2000]
                        task['status'] = 'approved'
                        task['checkpoints'].append({'number':len(task['checkpoints'])+1,'decision':'APPROVE','feedback':item['outcome_summary'], 'diff':current['patch'],'branch_candidate_id':current['id']})
                        engine.event(task,'review','Independent item review passed',{'item_id':item['id'],'candidate_id':current['id']})
                        return {'decision':'APPROVE','feedback':item['outcome_summary']}
                elif choice in {'REQUEST_CHANGES', 'TAKE_OVER'} and isinstance(params.get('feedback'),str):
                    task.pop('pending_review',None)
                    task['status'] = 'running' if choice == 'REQUEST_CHANGES' else 'takeover_requested'
                    branch_runs.transition_item(run, item['id'], 'working')
                    engine.event(task,'review','Item needs revision',{'item_id':item['id'],'decision':choice,'feedback':params['feedback'][:4000]})
                    return {'decision':choice,'feedback':params['feedback'][:4000]}
                else: result = {'error':'Return a valid independent review decision.'}
            elif name in {'read_file','outline_file','search','list_files','get_diff','read_check_output'}:
                try: result = engine.file_tool(task,name,params)
                except (ValueError,OSError,TypeError,UnicodeError) as error: result = {'error':str(error)[:1000]}
            elif name == 'read_url': result = engine.read_url(runtime,params)
            else: result = {'error':'Review tools are read-only.'}
            messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result)})
    raise ProgressPause('Independent review reached its eight-request limit without a valid decision.')
