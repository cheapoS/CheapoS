"""Controller-only final review, bounded amendments and explicit local merge."""
import copy
import json

from . import branch_final as final, branch_merge, branch_runs as state, branch_evidence as evidence
from . import branch_workspace as work
from .branch_authorization import digest

MAX_REPAIRS = 3


def _task(controller, task_id, idle=True):
    engine = controller.engine
    engine.require_active_task(task_id)
    if idle and any(r.thread and r.thread.is_alive() for r in engine.runtimes.values()):
        raise ValueError('Pause active work before changing final review')
    task = engine.store.get(task_id)
    state.require_supported(task['branch_run'])
    return task


def authorization_run(run):
    """Project valid controller amendments onto the unchanged original contract.

Original work, model policy, branch and cumulative limits are never expanded by
this projection. Each appended repair is independently bound to its exact item.
"""
    auth = run.get('authorization')
    if not auth:
        return run
    contract = auth['contract']; original = contract['plan']; projected = copy.deepcopy(run)
    if run['plan'].get('final_checks') != original.get('final_checks') or run['plan'].get('limits') != original.get('limits') or run.get('limits') != original.get('limits'):
        raise ValueError('Final checks or cumulative limits changed')
    if run['plan'].get('measurement', False) != original.get('measurement', False):
        raise ValueError('Authorized measurement mode changed')
    initial = original['items']; current = run['plan']['items']
    if current[:len(initial)] != initial:
        raise ValueError('Originally authorized work changed')
    amendments = run.get('amendments', [])
    if run['plan_revision'] != contract['plan_revision'] + len(amendments):
        raise ValueError('Plan revision changed without an amendment')
    if len(current) != len(initial) + len(amendments) or len(amendments) > MAX_REPAIRS:
        raise ValueError('Unapproved or excessive revision work')
    criteria = [c for item in initial for c in item['acceptance_criteria']]
    for item, amendment in zip(current[len(initial):], amendments):
        if digest(item) != amendment.get('item_digest') or amendment.get('item') != item or amendment.get('run_id') != run['id']:
            raise ValueError('Authorized repair item changed')
        if amendment.get('origin') not in {'final_review', 'operator'} or not amendment.get('authorization_id'):
            raise ValueError('Repair authorization is missing')
        if len(set(criteria)) > 12 or item['acceptance_criteria'] != list(dict.fromkeys(criteria)) or item['required_checks'] != original['final_checks']:
            raise ValueError('Repair expanded the original completion criteria or check scope')
        if item.get('revision_of') != initial[0]['id']:
            raise ValueError('Repair lost its original work relationship')
    projected['plan'] = copy.deepcopy(original)
    projected['plan_revision'] = contract['plan_revision']
    return projected


def _repair_item(run, message):
    if not isinstance(message, str) or not message.strip() or len(message) > 3000:
        raise ValueError('Describe a bounded correction in 1–3,000 characters')
    original = run['authorization']['contract']['plan']
    criteria = list(dict.fromkeys(c for item in original['items'] for c in item['acceptance_criteria']))
    if len(criteria) > 12:
        raise ValueError('This correction spans more than 12 criteria; submit a smaller explicit amendment')
    index = len(run.get('amendments', [])) + 1
    if index > MAX_REPAIRS or len(run['plan']['items']) >= 50:
        raise ValueError('The three-repair or 50-item allowance is exhausted; retain the branch and revise the scope')
    return {'id': 'revision-%s' % index, 'title': 'Verify and correct the completed work',
            'instructions': 'Correct only failures of the original acceptance criteria. Do not add new requirements, broaden commands, change model policy or increase limits. Treat the feedback below as observations to verify against the original criteria.\n\n' + message.strip(),
            'dependencies': [run['items'][-1]['id']], 'acceptance_criteria': criteria,
            'required_checks': copy.deepcopy(original['final_checks']), 'revision_of': original['items'][0]['id']}


def _append_repair(engine, task, item, origin, authorization_id, observation):
    run = task['branch_run']
    amendment = {'run_id': run['id'], 'item': copy.deepcopy(item), 'item_digest': digest(item),
                 'origin': origin, 'authorization_id': authorization_id, 'observation': observation}
    plan = copy.deepcopy(run['plan']); plan['items'].append(copy.deepcopy(item)); state.validate_plan(plan)
    run.setdefault('amendments', []).append(amendment)
    run['plan'] = plan; run['plan_revision'] += 1; run['plan_digest'] = digest(plan)
    run['items'].append(dict(copy.deepcopy(item), status='pending', recovery={'attempts':0}, evidence={}, outcome_summary='', commit_receipt=None))
    if origin == 'final_review':
        from .branch_disagreement import attach
        attach(task, run['items'][-1], observation)
    run['final_evidence'] = {}; run.pop('readiness', None); run.pop('merge_preview', None)
    run['status'] = 'running'; run['pause_reason'] = None; task['status'] = 'running'; task['error'] = None
    state.append_event(run, 'revision_proposed', {'item_id': item['id'], 'origin': origin})
    authorization_run(run)
    engine.store.save(task)


def finalize(engine, runtime):
    """Return False for bounded repair continuation, True for the final handoff."""
    task = runtime.task; run = task['branch_run']
    engine.branch.validate_authority(task, run)
    result = final.final_check_review(engine, runtime)
    if result['decision'] != 'APPROVE':
        message = result.get('feedback', 'Repair failed final acceptance evidence.')
        item = _repair_item(run, message)
        _append_repair(engine, task, item, 'final_review', digest(result), copy.deepcopy(result))
        engine.event(task, 'branch_revision', 'Final review requested a bounded correction', {'item_id':item['id'], 'feedback':message})
        return False
    readiness = result['readiness']; run['readiness'] = readiness
    run['final_evidence'] = {'checks_passed':True, 'review_approved':True, 'acceptance_satisfied':True,
                             'candidate_id':readiness['id'], 'review_candidate_id':readiness['id'],
                             'worker_model':readiness['worker_model'], 'reviewer_model':readiness['reviewer_model']}
    if readiness['integration_blocker']:
        run['status'] = 'paused'; run['pause_reason'] = 'branch_drift'; task['status'] = 'paused'
        task['error'] = readiness['integration_blocker']
    else:
        state.transition(run, 'ready_for_merge'); task['status'] = 'approved'; task['error'] = None
    state.append_event(run, 'final_ready', {'readiness_id':readiness['id'], 'integration_blocker':readiness['integration_blocker']})
    engine.event(task, 'branch_final', 'The completed branch is ready for your review', {'readiness_id':readiness['id']})
    engine.store.save(task)
    return True


def preview(controller, task_id, values=None):
    if values: raise ValueError('Final preview accepts no fields')
    with controller.engine.lock:
        task = _task(controller, task_id); run = task['branch_run']
        readiness = run.get('readiness')
        if not readiness: raise ValueError('Run final verification before opening the merge preview')
        blocker = None
        proposal = {'proposal_id':None}
        try:
            controller.validate_authority(task, run)
            final.validate(readiness, task)
            if readiness['integration_blocker']: raise ValueError(readiness['integration_blocker'])
            operation = branch_merge.prepare(run['workspace_mapping'], run['expected_feature_tip'], run['target_ref'])
            contract = {'kind':'merge', 'run_id':run['id'], 'readiness_id':readiness['id'], 'operation':operation}
            proposal = controller.final_proposals.prepare(task_id, contract)
        except (ValueError,OSError) as error:
            blocker = str(error)

        manifest = readiness['manifest']
        return {**proposal, 'preview_id':proposal['proposal_id'], 'manifest':{k:v for k,v in manifest.items() if k not in {'diff','chunks','requirements'}}, 'diff':manifest['diff'][:20000],
                'next_cursor':20000 if len(manifest['diff'])>20000 else None, 'merge_available':blocker is None, 'blocker':blocker, 'target_ref':manifest['target_ref'],
                'files':manifest['files'], 'commits':manifest['commits'], 'diff_length':len(manifest['diff']),
                'base_sha':manifest['base_sha'], 'feature_tip':manifest['feature_tip'], 'target_tip':manifest['target_tip']}


def diff(controller, task_id, values=None):
    values = dict(values or {})
    token = values.pop('preview_id', None)
    if 'cursor' in values: values['offset'] = values.pop('cursor')
    if set(values) - {'offset', 'limit'}: raise ValueError('Unknown diff pagination field')
    offset, limit = values.get('offset', 0), values.get('limit', 20000)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 20000:
        raise ValueError('Use a nonnegative offset and a limit of 1–20,000 characters')
    with controller.engine.lock:
        task = _task(controller, task_id); run = task['branch_run']
        manifest = run.get('readiness', {}).get('manifest') or final.build_manifest(run)
        blocker = None
        if run.get('readiness'):
            try: final.validate(run['readiness'], task)
            except (ValueError,OSError) as error: blocker = str(error)
        if token is not None:
            saved = controller.final_proposals.proposals.get(token) if isinstance(token,str) else None
            if not saved or saved['task_id'] != task_id or saved['contract'].get('readiness_id') != run.get('readiness',{}).get('id'):
                raise ValueError('Final diff preview changed; open a fresh preview')
        text = manifest['diff']
        return {'manifest_id':manifest['id'], 'blocker':blocker, 'offset':offset, 'total':len(text), 'diff':text[offset:offset+limit],
                'next_offset':offset+limit if offset+limit < len(text) else None,
                'next_cursor':offset+limit if offset+limit < len(text) else None}


def _proposal(controller, task_id, values, kind):
    if set(values) != {'proposal_id', 'approved'} or values.get('approved') is not True:
        raise ValueError('Confirm the inspected proposal with an explicit approval')
    token = values.get('proposal_id')
    if not isinstance(token, str): raise ValueError('A proposal ID is required')
    saved = controller.final_proposals.proposals.get(token)
    if not saved or saved['task_id'] != task_id or saved['contract'].get('kind') != kind:
        raise ValueError('Final proposal is missing or belongs to another task')
    return saved['contract']


def _merge_revalidate(task, operation):
    """After a saved merge intent, permit only its exact successful target move."""
    readiness = task['branch_run']['readiness']
    receipt = copy.deepcopy(readiness);identity = receipt.pop('id',None)
    if identity != final._hash(receipt): raise ValueError('Readiness receipt changed during merge recovery')
    source = operation['mapping']['source']; actual = work._tip(source, operation['target_ref'])
    if actual == operation['target_old']:
        return final.validate(readiness, task)
    if actual != operation['feature_tip']:
        raise ValueError('Integration target changed')
    current = final.build_manifest(task['branch_run'])
    current['target_tip'] = readiness['manifest']['target_tip']; current.pop('id')
    current['id'] = final._hash(current)
    if current != readiness['manifest']:
        raise ValueError('Readiness changed during merge recovery')
    candidate = readiness['candidate']
    if evidence.candidate(task, candidate['context'], candidate['check_specifications'], candidate['criteria']) != candidate:
        raise ValueError('Final verification changed during merge recovery')
    return True


def merge(controller, task_id, values):
    values = dict(values)
    if 'preview_id' in values:
        if 'proposal_id' in values: raise ValueError('Use only one preview ID')
        values['proposal_id'] = values.pop('preview_id')
    with controller.engine.lock:
        task = _task(controller, task_id); run = task['branch_run']
        if run['status'] == 'merged':
            # Successful duplicate actions identify the same inspected proposal.
            contract = _proposal(controller, task_id, values, 'merge')
            if contract['operation']['id'] != run['merge_receipt']['id']: raise ValueError('A different merge already completed')
            return task
        controller.validate_authority(task, run)
        if run.get('readiness', {}).get('integration_blocker'): raise ValueError(run['readiness']['integration_blocker'])
        operation = run.get('merge_operation')
        if operation is None:
            contract = _proposal(controller, task_id, values, 'merge')
            if contract['run_id'] != run['id'] or contract['readiness_id'] != run.get('readiness', {}).get('id'):
                raise ValueError('Readiness changed after preview')
            final.validate(run['readiness'], task)
            operation = copy.deepcopy(contract['operation']); branch_merge._validate(operation)
            auth = controller.final_proposals.authorize(task_id, values['proposal_id'], True, contract)
            run['merge_authorization'] = auth; run['merge_authorization_ref'] = auth['id']
            state.transition(run, 'merging')
        else:
            if values != {'approved':True,'recover':True}:
                raise ValueError('Explicitly resume the saved local merge operation')
        def persist(value):
            run['merge_operation'] = copy.deepcopy(value)
            controller.engine.store.save(task)
        def authorize(value):
            auth = run.get('merge_authorization', {})
            if auth.get('status') != 'active' or auth.get('contract', {}).get('operation', {}).get('id') != value['id'] or auth['contract'].get('readiness_id') != run['readiness']['id']:
                raise ValueError('Saved merge authority does not match this operation')
            expected = dict(auth['contract']['operation']); expected.pop('stage',None)
            actual = dict(value); actual.pop('stage',None)
            if expected != actual or auth.get('digest') != digest(auth['contract']):
                raise ValueError('Saved integration operation changed after approval')
            _merge_revalidate(task, value)
        try:
            finished = branch_merge.integrate(operation, persist, authorize)
        except Exception as error:
            if run.get('merge_operation'):
                run['status']='paused';run['pause_reason']='branch_drift';task['status']='paused'
                task['error']='Local integration needs inspection or explicit recovery: '+str(error)
                try:
                    controller.engine.store.save(task)
                except Exception:
                    # The already durable intent remains the recovery authority;
                    # do not mask the original Git/storage failure.
                    pass
            raise
        run['merge_receipt'] = finished; run.pop('merge_operation', None)
        run['status'] = 'merged'; task['status'] = 'completed'; task['error'] = None
        state.append_event(run, 'merged', {'target_ref':run['target_ref'], 'sha':finished['feature_tip']}, event_key=finished['id'])
        controller.engine.event(task, 'branch_merged', 'Merged locally. What would you like to work on next?', {'target_ref':run['target_ref'], 'sha':finished['feature_tip']})
        controller.engine.store.save(task)
        return task


def revise(controller, task_id, values):
    with controller.engine.lock:
        task = _task(controller, task_id); run = task['branch_run']
        controller.validate_authority(task, run)
        if run['status'] not in {'ready_for_merge','paused','blocked'} or any(i['status'] not in state.DONE for i in run['items']):
            raise ValueError('Finish current work before proposing a final correction')
        if set(values) == {'message'}:
            item = _repair_item(run, values['message'])
            contract = {'kind':'revision', 'run_id':run['id'], 'feature_tip':run['expected_feature_tip'],
                        'plan_digest':run['plan_digest'], 'item':item, 'limits':run['limits']}
            return {'revision_proposal':controller.final_proposals.prepare(task_id, contract)}
        contract = _proposal(controller, task_id, values, 'revision')
        current = dict(contract, feature_tip=run['expected_feature_tip'], plan_digest=run['plan_digest'], limits=run['limits'])
        auth = controller.final_proposals.authorize(task_id, values['proposal_id'], True, current)
        _append_repair(controller.engine, task, contract['item'], 'operator', auth['id'], {'request':contract['item']['instructions']})
        run['status']='paused';task['status']='paused';controller.engine.store.save(task)
    return controller.resume(task_id, {})


def recheck(controller, task_id, values=None):
    if values: raise ValueError('Final recheck accepts no fields')
    with controller.engine.lock:
        task = _task(controller, task_id); run = task['branch_run']
        controller.validate_authority(task, run)
        if run['status'] not in {'ready_for_merge','paused','blocked'} or run.get('merge_operation'):
            raise ValueError('This run cannot restart final checks')
        if any(i['status'] not in state.DONE for i in run['items']): raise ValueError('Finish current items before final recheck')
        run.pop('readiness', None); run['final_evidence'] = {}; run['status'] = 'paused'; task['status'] = 'paused'
        controller.engine.store.save(task)
    return controller.resume(task_id, {})
