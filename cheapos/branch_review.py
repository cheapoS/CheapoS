"""Independent item review, using actual checks and captured acceptance criteria."""
import copy
import json
import shlex
import hashlib

import time

from . import branch_evidence as evidence
from . import branch_runs, branch_disagreement as disagreement
from .measurement import enabled as measuring
from .providers import ProviderError


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
    from . import review_disputes
    if item.get('review_repair'):
        disagreement.pending(task,item)
        review_disputes.dispositions(task,item,args,current['id'])
    plan_for_review = copy.deepcopy(run['plan'])
    if isinstance(plan_for_review, dict) and 'items' in plan_for_review:
        for it in plan_for_review.get('items', []):
            if isinstance(it, dict):
                it.pop('review_repair', None)
    item_for_review = {k: v for k, v in item.items() if k != 'review_repair'}
    packet = evidence.review_packet(current, item_for_review, plan_for_review, checks, str(args.get('uncertainties', ''))[:2000])
    if item.get('review_repair'):
        packet['repair_review']=review_disputes.brief(item['review_repair'])
        import difflib
        packet['repair_diff_since_claim']=''.join(difflib.unified_diff(item['review_repair'].get('source_patch','').splitlines(True),current['patch'].splitlines(True),fromfile='disputed candidate patch',tofile='current candidate patch',n=3))
        packet['worker_summary']=str(args.get('summary',''))[:4000]
    if len(json.dumps(packet)) > 30000:
        raise ProgressPause('Item review exceeds 30,000 characters. Split the item in a revised proposal; no evidence was omitted.')
    branch_runs.transition_item(run, item['id'], 'reviewing')
    tools = copy.deepcopy(REVIEW_TOOLS)
    decision = next(t for t in tools if t['function']['name'] == 'review_decision')['function']['parameters']
    outcome = {'type':'object','properties':{'passed':{'type':'boolean'},'evidence':{'type':'string'}},'required':['passed','evidence'],'additionalProperties':False}
    decision['properties'].update(candidate_id={'type':'string','enum':[current['id']]}, criteria_outcomes={'type':'object', 'description':'Use every exact criterion key. passed is a JSON boolean, evidence is a nonempty string.', 'properties':{c:copy.deepcopy(outcome) for c in criteria},'required':list(criteria),'additionalProperties':False})
    decision['properties']['suggestions']={'type':'array','maxItems':8,'items':{'type':'string'}}
    decision['properties']['defects'] = disagreement.schema(criteria)
    decision['required'] += ['candidate_id','criteria_outcomes']
    diff_notice = ' If packet diff is empty, the change may already be present in the repository from earlier commits; if files and passing checks satisfy the criteria, call review_decision with APPROVE.' if not packet.get('diff') else ''
    direct_call = ' Do not output conversational text or preamble. Call review_decision directly as your tool call.'
    messages = [{'role':'system','content':REVIEW_SYSTEM+' This is an Unattended item. Return the exact candidate_id and evidence for every acceptance criterion. APPROVE requires the whole item, not only a partial checkpoint.' + diff_notice + direct_call + disagreement.REVIEW_INSTRUCTION}, {'role':'user','content':json.dumps(packet)}]
    if task.get('pending_review',{}).get('branch_candidate_id')!=current['id']:
        task['pending_review']={'branch_candidate_id':current['id'],'review_requests':0}
    task['status'] = 'reviewing'
    engine.event(task, 'checkpoint', 'Reviewing the complete branch item', {'item_id':item['id'], 'candidate_id':current['id']})
    rounds = 0
    while measuring(task) or rounds < 8:
        rounds += 1
        disagreement.ensure_available(task, current['id'])
        runtime.guard()
        engine.event(task,'review_request','Requesting item review',{'item_id':item['id'],'candidate_id':current['id']})
        message = engine.request(runtime, messages, tools, 'reviewer')
        task['review_count'] += 1
        messages.append(message)
        calls = message.get('tool_calls', [])
        if len(calls) > 8:
            raise ProgressPause('Reviewer exceeded the bounded tool-call allowance.')
        if not calls:
            messages.append({'role':'user','content':'Call review_decision with the candidate ID and every criterion outcome.'})
        observations = []
        for call in calls:
            if runtime.stop.is_set(): raise InterruptedError('Task stopped')
            name, params = engine.parse_call(call)
            if name == 'review_decision':
                try:
                    choice = disagreement.decision(params, takeover=True)
                    params['decision'] = choice
                except ValueError as error:
                    result = disagreement.unsupported(engine, task, current['id'], params, error)
                    messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result)})
                    continue
                if choice == 'APPROVE':
                    try:
                        receipt = evidence.ready_receipt(current, checks, params, task['providers']['worker'], task['providers']['reviewer'], params.get('criteria_outcomes'))
                        evidence.revalidate(receipt, task, ctx, specs, criteria)
                    except ValueError as error:
                        result = disagreement.unsupported(engine,task,current['id'],params,error)
                    else:
                        review_disputes.resolved(task,item,current['id'])
                        task.pop('pending_review',None)
                        item['ready_receipt'] = receipt
                        item['outcome_summary'] = str(params.get('feedback',''))[:2000]
                        task['status'] = 'approved'
                        task['checkpoints'].append({'number':len(task['checkpoints'])+1,'decision':'APPROVE','feedback':item['outcome_summary'], 'diff':current['patch'],'branch_candidate_id':current['id']})
                        engine.event(task,'review','Independent item review passed',{'item_id':item['id'],'candidate_id':current['id'],'decision':'APPROVE','feedback':item['outcome_summary']})
                        return {'decision':'APPROVE','feedback':item['outcome_summary']}
                elif choice in {'REQUEST_CHANGES', 'TAKE_OVER'} and isinstance(params.get('feedback'),str):
                    try:
                        if params.get('candidate_id') != current['id']:
                            raise ValueError('Review disagreement belongs to a stale candidate.')
                        if choice == 'REQUEST_CHANGES':
                            params['defects'] = disagreement.validate(params, criteria)
                            # A reviewer read tool cannot silently change the reviewed inputs.
                            if evidence.candidate(task, ctx, specs, criteria) != current:
                                raise ValueError('Candidate changed during review disagreement.')
                    except ValueError as error:
                        result = disagreement.unsupported(engine, task, current['id'], params, error)
                    else:
                        task.pop('pending_review',None)
                        task['status'] = 'running' if choice == 'REQUEST_CHANGES' else 'takeover_requested'
                        branch_runs.transition_item(run, item['id'], 'working')
                        result = disagreement.repair(params, current['id'], checks)
                        if choice == 'REQUEST_CHANGES':
                            result['source_patch']=current['patch']
                            refs=item.get('review_repair',{}).get('requirement_refs')
                            if refs:result['requirement_refs']=copy.deepcopy(refs)
                            disagreement.attach(task, item, result)
                            engine.event(task,'repair_attempt','Preparing focused item repair',{'item_id':item['id'],'candidate_id':current['id'],'finding_ids':item['review_repair']['finding_ids']})
                        engine.event(task,'review','Actionable item review claim' if choice == 'REQUEST_CHANGES' else 'Item needs takeover',
                                     {'item_id':item['id'],'decision':choice,'feedback':params['feedback'][:4000],
                                      'defects':params.get('defects'), 'candidate_id':current['id']})
                        engine.store.save(task)
                        return result
                else: result = {'error':'Return a valid independent review decision.'}
            elif name in {'read_file','outline_file','search','list_files','get_diff','read_check_output'}:
                try: result = engine.file_tool(task,name,params)
                except (ValueError,OSError,TypeError,UnicodeError) as error: result = {'error':str(error)[:1000]}
            elif name == 'read_url': result = engine.read_url(runtime,params)
            else: result = {'error':'Review tools are read-only.'}
            messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result)})
            observations.append({'name':name,'parameters':params,'result':result})
        # Measurement removes cumulative request caps, not endless identical
        # reads or invalid decisions. Keep this evidence with the candidate so
        # restarting or resuming cannot renew the same unsuccessful attempts.
        fingerprint = hashlib.sha256(json.dumps(observations,sort_keys=True).encode()).hexdigest()
        repeated = task['pending_review'].setdefault('observations',{})
        repeated[fingerprint] = repeated.get(fingerprint,0) + 1
        engine.store.save(task)
        if repeated[fingerprint] >= 3:
            raise ProgressPause('Independent review repeated the same evidence or invalid response three times. Saved review evidence is retained.')
    raise ProgressPause('Independent review reached its eight-request limit without a valid decision.')
