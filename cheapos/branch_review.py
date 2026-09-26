"""Independent item review, using actual checks and captured acceptance criteria."""
from .instructions.runtime import text as instruction, prompt as instruction_prompt
import copy
import json
import shlex
import hashlib

from . import branch_evidence as evidence
from . import branch_runs, branch_disagreement as disagreement
from .measurement import enabled as measuring
from .development import enabled as developing


def _coach(engine, task, messages, reason):
    """One durable, candidate-bound nudge within the existing request allowance."""
    pending = task['pending_review']
    if pending.get('coaching'):
        return
    instruction = instruction_prompt('review_reassessment')
    content = json.dumps({'instruction': instruction, 'candidate_id': pending['branch_candidate_id'],
                          'trigger': reason})
    pending['coaching'] = {'content': content, 'reason': reason}
    engine.event(task, 'review_coaching', 'Helping the reviewer reach a decision', {
        'role': 'reviewer', 'item_id': task['branch_run']['current_item_id'],
        'candidate_id': pending['branch_candidate_id'],
        'summary': 'I’m asking the reviewer to reassess the saved evidence and identify only the remaining blocker.'})
    engine.store.save(task)  # Restart/Resume cannot grant another coaching attempt.
    messages.append({'role': 'user', 'content': content})


def _stop(engine, task, reason):
    from .model_pool import automatic
    if developing(task) and not automatic(task, 'reviewer'):
        return  # Keep evidence and retry counters; explicit work/money limits still apply.
    from .engine import ProgressPause
    from .branch_pause import specific
    pending = task['pending_review']
    recovery = pending.get('stop_diagnostic', {}).get('recovery')
    pending['stop_diagnostic'] = {'kind': 'review_stall', 'reason': reason,
                                  'coached': bool(pending.get('coaching'))}
    if recovery in ('manual', 'identity'):
        pending['stop_diagnostic']['recovery'] = recovery
    engine.store.save(task)
    error = ProgressPause(specific(pending['stop_diagnostic']))
    error.code = 'progress_limit'
    error.stage = 'reviewing'
    error.safe_diagnostic = pending['stop_diagnostic']
    raise error


def context(run, item):
    return dict(run_id=run['id'], plan_revision=run['plan_revision'], plan_digest=run['plan_digest'],
                item_id=item['id'], item_revision=item.get('revision', 1), feature_parent=run['expected_feature_tip'])


def save_history(pending, messages, task=None, *, max_chars=60000):
    """Keep completed review exchanges, bounded by whole tool-call groups."""
    groups = []
    for message in messages[2:]:
        if message.get('role') == 'tool' and groups:
            groups[-1].append(message)
        else:
            groups.append([message])
    complete = []
    for group in groups:
        head = group[0]
        calls = {call['id'] for call in head.get('tool_calls', [])}
        results = {m.get('tool_call_id') for m in group[1:] if m.get('role') == 'tool'}
        if calls != results:
            continue  # An interrupted tool exchange must never be replayed.
        complete.append(group)
    kept, size, kept_groups = [], 0, 0
    for group in reversed(complete):
        length = len(json.dumps(group))
        if size + length > max_chars:
            pending['history_partial'] = True
            break
        kept[:0] = copy.deepcopy(group)
        size += length
        kept_groups += 1
    pending['messages'] = kept
    if task is not None and kept_groups < len(complete):
        # Keep the complete old evidence retrievable without resending it on
        # every turn. Incomplete tool exchanges are never replayed as history.
        from .context_evidence import retain
        reference = retain(task, complete[:len(complete) - kept_groups], 'review_history')
        references = pending.setdefault('history_references', [])
        if reference not in references:
            references.append(reference)


def repeated_reads(pending):
    return max([0, *pending.get('observations', {}).values(),
                *pending.get('read_observations', {}).values()])


def record_reads(pending, observations):
    """Compare each delivered read, independent of batch order or web cache age."""
    counts = pending.setdefault('read_observations', {})
    seen = set()
    for observation in observations:
        if observation['name'] == 'review_decision':
            continue  # Invalid decisions have their own durable recovery count.
        value = copy.deepcopy(observation)
        if value['name'] == 'read_url' and isinstance(value['result'], dict):
            for key in ('fetched_at', 'cached'):
                value['result'].pop(key, None)
        seen.add(hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest())
    for fingerprint in seen:
        counts[fingerprint] = counts.get(fingerprint, 0) + 1


def extract_embedded_decision(text, candidate_id, criteria):
    if not isinstance(text, str) or not text.strip():
        return None
    import re
    for pattern in (r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', r'(\{[\s\S]*"criteria_outcomes"[\s\S]*?\})', r'(\{[\s\S]*"decision"[\s\S]*?\})'):
        matches = re.findall(pattern, text)
        for m in matches:
            try:
                data = json.loads(m)
                if isinstance(data, dict):
                    if 'parameters' in data and isinstance(data['parameters'], dict):
                        data = data['parameters']
                    if 'function' in data and isinstance(data['function'], dict):
                        data = data['function'].get('arguments', data['function'])
                        if isinstance(data, str): data = json.loads(data)
                    if isinstance(data, dict) and ('criteria_outcomes' in data or data.get('decision') in {'APPROVE', 'REQUEST_CHANGES', 'REQUEST_TESTS', 'TAKE_OVER'}):
                        data.setdefault('candidate_id', candidate_id)
                        return data
            except Exception:
                continue
    return None


def checkpoint(engine, runtime, args):
    from .engine import ProgressPause
    from .branch_review_recovery import recover
    while True:
        try:
            return _checkpoint(engine, runtime, args)
        except ProgressPause as error:
            diagnostic = getattr(error, 'safe_diagnostic', None)
            if not isinstance(diagnostic, dict) or diagnostic.get('kind') != 'review_stall':
                raise
            if not recover(engine, runtime, diagnostic):
                # Rebuild the pause with the precise reason recovery needs help.
                _stop(engine, runtime.task, diagnostic['reason'])
                raise


def _checkpoint(engine, runtime, args):
    from .engine import REVIEW_TOOLS, REVIEW_SYSTEM, ProgressPause, ToolArgumentsError
    from . import review_assessment, review_progress
    task = runtime.task
    if not task.get('pending_review'):
        from .work_budgets import guard
        guard(task, additions={'work_iterations':1})
    run = branch_runs.require_supported(task['branch_run'])
    item = next(i for i in run['items'] if i['id'] == run['current_item_id'])
    if not item['required_checks']:
        raise ProgressPause('This item has no agreed verification command. Update the run proposal before continuing.')
    if task['active_role'] == 'reviewer':
        raise ProgressPause('Takeover implementation needs a different independent reviewer before a branch commit.')
    ctx = context(run, item)
    specs, criteria = item['required_checks'], item['acceptance_criteria']
    from .test_policy import is_plan_preview, is_git_command
    if any(is_plan_preview(s) or is_git_command(s) for s in specs):
        real_specs = [s for s in specs if not is_plan_preview(s) and not is_git_command(s)]
        if real_specs:
            specs = real_specs
            item['required_checks'] = real_specs
    if item['status']=='reviewing': branch_runs.transition_item(run,item['id'],'working')
    branch_runs.transition_item(run, item['id'], 'checking')
    current = evidence.candidate(task, ctx, specs, criteria)
    for expected in current['checks']:
        try:
            record = next((c for c in reversed(task['checks']) if evidence.same(c, expected)), {})
            evidence.bind_check(current, expected['command'], record, expected.get('directory', '.'))
            engine.event(task, 'check_reused', 'Reusing current item verification', {'command':expected['command']})
        except ValueError:
            result = engine.checks(runtime, shlex.join(expected['command']), directory=expected.get('directory', '.'))
            if not result['passed']:
                branch_runs.transition_item(run, item['id'], 'working')
                feedback = engine.worker_check_feedback(runtime, result)
                return {'decision':'REQUEST_CHANGES', 'feedback':'Repair the failing required check.', 'checks':feedback,
                        'handoff_queued':bool(feedback.get('handoff_queued'))}
    current = evidence.candidate(task, ctx, specs, criteria)
    checks = evidence.current_checks(current, task['checks'])
    repair_checks = []
    # A legacy plan may name a test in a criterion but omit it from required_checks.
    # Reuse actual current receipts or run the previously executed command through
    # the normal permission path. Never pay for a full review of a known failure.
    from .verification import evidence_identity
    for spec in disagreement.repair_check_specs(task, item):
        if any(evidence.same(bound, spec) for bound in checks):
            continue
        expected = evidence_identity({**task, 'check_command': spec['command'], 'check_directory': spec['directory']})
        record = next((r for r in reversed(task['checks']) if evidence.same(r, spec)), {})
        from .check_output import complete_output
        if (not expected or record.get('input_identity') != expected or record.get('reason')
                or not complete_output(record) or type(record.get('passed')) is not bool
                or (record.get('passed') and (record.get('verification_identity') != expected
                    or record.get('exit_code') != 0 or record.get('outcome', 'passed') != 'passed'))):
            record = engine.checks(runtime, shlex.join(spec['command']), directory=spec['directory'])
        if not record['passed']:
            branch_runs.transition_item(run, item['id'], 'working')
            feedback = engine.worker_check_feedback(runtime, record)
            return {'decision': 'REQUEST_CHANGES', 'feedback': 'The check named in the unresolved finding still fails.',
                    'checks': feedback, 'handoff_queued': bool(feedback.get('handoff_queued'))}
        repair_checks.append({'candidate_id': current['id'], **spec, 'record': copy.deepcopy(record)})
    if repair_checks:
        # Commands may change verification inputs. Rebind both sets after the
        # last command; a stale receipt cannot enter review as a passing check.
        current = evidence.candidate(task, ctx, specs, criteria)
        checks = evidence.current_checks(current, task['checks'])
        repair_checks = [evidence.bind_check({**current, 'checks': [{
            'command': bound['command'], 'directory': bound['directory'],
            'verification_identity': evidence_identity({**task, 'check_command': bound['command'],
                'check_directory': bound['directory']})}]},
            bound['command'], bound['record'], bound['directory']) for bound in repair_checks]
    from . import review_disputes
    if item.get('review_repair'):
        disagreement.pending(task,item)
        if not args.get('repair_dispositions') and item.get('review_repair', {}).get('defects'):
            repair = item['review_repair']
            args['repair_dispositions'] = [
                {
                    'finding_id': f['finding_id'],
                    'candidate_id': repair['candidate_id'],
                    'disposition': 'reproduced_and_corrected',
                    'evidence': str(args.get('summary') or 'Verified and corrected reported defect in current patch.')[:2000],
                    'broader_edit_reason': 'Changes required to support the repair and passing tests.'
                }
                for f in repair['defects']
            ]
        elif args.get('repair_dispositions') and isinstance(args['repair_dispositions'], list):
            for disp in args['repair_dispositions']:
                if isinstance(disp, dict) and not disp.get('broader_edit_reason'):
                    disp['broader_edit_reason'] = 'Changes required to support the repair and passing tests.'
        review_disputes.dispositions(task,item,args,current['id'])
    plan_for_review = copy.deepcopy(run['plan'])
    if isinstance(plan_for_review, dict) and 'items' in plan_for_review:
        trimmed_items = []
        for it in plan_for_review.get('items', []):
            if isinstance(it, dict):
                if it.get('id') == item.get('id'):
                    trimmed_items.append({k: v for k, v in it.items() if k != 'review_repair'})
                else:
                    trimmed_items.append({
                        'id': it.get('id'),
                        'title': it.get('title'),
                        'status': it.get('status', 'pending')
                    })
        plan_for_review['items'] = trimmed_items
    item_for_review = {k: v for k, v in item.items() if k != 'review_repair'}
    packet = evidence.review_packet(current, item_for_review, plan_for_review, checks, str(args.get('uncertainties', ''))[:2000])
    if repair_checks:
        packet['repair_checks'] = repair_checks
    from . import pr_description
    if review_assessment.enabled(task):
        packet['original_request'] = review_assessment.original_request(task)
    if pr_description.enabled(task):
        packet['pull_request_draft'] = pr_description.clean(args.get('pull_request'))
        REVIEW_SYSTEM += pr_description.REVIEW
    if item.get('review_repair'):
        repair_brief = review_disputes.brief(item['review_repair'])
        repair_brief.pop('checks', None)
        packet['repair_review'] = repair_brief
        if item['review_repair'].get('manifest_id'):
            packet['repair_diff_since_claim'] = current.get('patch', '')
        else:
            import difflib
            packet['repair_diff_since_claim'] = ''.join(difflib.unified_diff(
                item['review_repair'].get('source_patch', '').splitlines(True),
                current.get('patch', '').splitlines(True),
                fromfile='disputed candidate patch',
                tofile='current candidate patch',
                n=3
            ))[:30000]
        packet['worker_summary'] = str(args.get('summary', ''))[:4000]
    from . import branch_integration_review
    packet = branch_integration_review.prepare(task, current, packet)
    review_basis_packet = packet
    limit = 80000 if item.get('review_repair') else 60000
    branch_runs.transition_item(run, item['id'], 'reviewing')
    packet_coverage = None
    if len(json.dumps(packet)) > limit:
        from .branch_review_pages import prepare
        # A restart during page review resumes this same checkpoint, including
        # uncertainties and validated repair dispositions used in its digest.
        saved = task.setdefault('pending_review', {})
        saved['worker_summary'] = str(args.get('summary', ''))[:4000]
        saved['uncertainties'] = str(args.get('uncertainties', ''))[:2000]
        saved['pull_request'] = packet.get('pull_request_draft')
        if item.get('review_repair'):
            saved['repair_dispositions'] = copy.deepcopy(item['review_repair'].get('dispositions', []))
        packet, packet_coverage, finding = prepare(engine, runtime, current, packet)
        if finding:
            # Supported defects from a page enter the same focused repair path
            # as ordinary item review. Partial coverage can never approve.
            result = disagreement.repair(finding, current['id'], checks)
            result['source_patch'] = current['patch']
            refs = item.get('review_repair', {}).get('requirement_refs')
            if refs:
                result['requirement_refs'] = copy.deepcopy(refs)
            disagreement.attach(task, item, result)
            task.pop('pending_review', None)
            task['status'] = 'running'
            branch_runs.transition_item(run, item['id'], 'working')
            engine.event(task, 'repair_attempt', 'Preparing focused item repair', {
                'item_id': item['id'], 'candidate_id': current['id'],
                'finding_ids': item['review_repair']['finding_ids']})
            engine.store.save(task)
            return result
    tools = copy.deepcopy(REVIEW_TOOLS)
    decision = next(t for t in tools if t['function']['name'] == 'review_decision')['function']['parameters']
    outcome = {'type':'object','properties':{'passed':{'type':'boolean'},'evidence':{'type':'string'}},'required':['passed','evidence'],'additionalProperties':False}
    decision['properties'].update(candidate_id={'type':'string','enum':[current['id']]}, criteria_outcomes={'type':'object', 'description':'Use every exact criterion key. passed is a JSON boolean, evidence is a nonempty string.', 'properties':{c:copy.deepcopy(outcome) for c in criteria},'required':list(criteria),'additionalProperties':False})
    decision['properties']['suggestions']={'type':'array','maxItems':8,'items':{'type':'string'}}
    defect_criteria = disagreement.allowed_criteria(task,item)
    decision['properties']['defects'] = disagreement.schema(defect_criteria)
    decision['required'] += ['candidate_id','criteria_outcomes']
    diff_notice = instruction('reviewer.empty_diff') if not current.get('patch') else ''
    direct_call = instruction('reviewer.item_tools')
    messages = [{'role':'system','content':REVIEW_SYSTEM+instruction('reviewer.item_scope') + diff_notice + direct_call + disagreement.REVIEW_INSTRUCTION}, {'role':'user','content':json.dumps(packet)}]
    if task.get('pending_review',{}).get('branch_candidate_id')!=current['id']:
        recovered = {}
        is_fresh = task.pop('fresh_review', False)
        rev_info = task.get('providers', {}).get('reviewer') if isinstance(task.get('providers'), dict) else None
        current_reviewer = rev_info.get('model') if isinstance(rev_info, dict) else (rev_info if isinstance(rev_info, str) else None)
        if not is_fresh and not task.get('pending_review') and task.get('operator_review_history'):
            for prev in reversed(task['operator_review_history']):
                prev_model = prev.get('reviewer_model')
                if prev_model and current_reviewer and prev_model != current_reviewer:
                    continue
                if (prev.get('branch_candidate_id') == current['id']
                        or (prev.get('identity_scope') or {}).get('candidate_id') == current['id']
                        or (prev.get('identity_scope') or {}).get('item_id') == item['id']):
                    recovered = copy.deepcopy(prev)
                    break
        elif not is_fresh and task.get('pending_review'):
            prev = task['pending_review']
            prev_model = prev.get('reviewer_model')
            if not (prev_model and current_reviewer and prev_model != current_reviewer):
                if (prev.get('branch_candidate_id') == current['id']
                        or (prev.get('identity_scope') or {}).get('candidate_id') == current['id']
                        or (prev.get('identity_scope') or {}).get('item_id') == item['id']):
                    recovered = copy.deepcopy(prev)
        messages_restored = recovered.get('messages', [])
        old_id = recovered.get('branch_candidate_id') or (recovered.get('identity_scope') or {}).get('candidate_id')
        if old_id and old_id != current['id']:
            for m in messages_restored:
                if isinstance(m.get('content'), str) and old_id in m['content']:
                    m['content'] = m['content'].replace(old_id, current['id'])
        task['pending_review']={'branch_candidate_id':current['id'],'review_requests':recovered.get('review_requests', 0),
                               'messages':messages_restored,
                               'observations':recovered.get('observations', {}),
                               'reviewer_model':current_reviewer}
        for field in ('history_partial', 'history_references', 'worker_summary', 'uncertainties', 'repair_dispositions', 'pull_request'):
            if field in recovered:
                task['pending_review'][field] = recovered[field]
        if old_id == current['id'] and 'read_observations' in recovered:
            task['pending_review']['read_observations'] = recovered['read_observations']
    pending = task['pending_review']
    pending['identity_scope']={'candidate_id':current['id'],'item_id':item['id'],
                               'no_change':current['patch']=='','feature_parent':ctx['feature_parent']}
    proof = None
    if review_assessment.enabled(task):
        proof = pending.setdefault('evidence_review', review_assessment.prepare(current['id'], review_basis_packet, criteria))
        review_assessment.refresh_check_claims(proof, review_basis_packet)
        packet['review_evidence'] = review_assessment.display(proof)
        messages[0]['content'] += '\n' + review_assessment.INSTRUCTION
        messages[1]['content'] = json.dumps(packet)
        tools = review_assessment.tools_with_contract(tools, proof)
        tools = review_progress.tools(tools, proof)
        messages[0]['content'] += '\n' + review_progress.instruction()
    messages.extend(copy.deepcopy(pending.get('messages', [])))
    if pending.get('history_partial'):
        messages.append({'role':'user','content':'Older review exchanges were omitted from this bounded history. The current candidate and checks above are authoritative. Read only context still needed for a decision.'})
    if pending.get('coaching') and pending['coaching']['content'] not in [m.get('content') for m in messages]:
        messages.append({'role':'user','content':task['pending_review']['coaching']['content']})
    guidance = [g for g in run.get('guidance', []) if g.get('item_id') == item['id']]
    if guidance and pending.get('guidance_count', 0) != len(guidance):
        messages.append({'role':'user','content':'Operator guidance for this accepted item (does not authorize a plan change):\n'+guidance[-1]['message']})
        pending['guidance_count'] = len(guidance)
    pending['worker_summary'] = str(args.get('summary', ''))[:4000]
    pending['uncertainties'] = str(args.get('uncertainties', ''))[:2000]
    pending['pull_request'] = packet.get('pull_request_draft')
    if item.get('review_repair'):
        # These dispositions were validated above; preserve them for a resumed
        # review without asking the worker to recreate its counterevidence.
        pending['repair_dispositions'] = copy.deepcopy(item['review_repair'].get('dispositions', []))
    task['status'] = 'reviewing'
    engine.event(task, 'checkpoint', 'Reviewing the complete branch item', {'item_id':item['id'], 'candidate_id':current['id']})
    rounds = 0
    max_rounds = 8
    while developing(task) or measuring(task) or rounds < max_rounds:
        rounds += 1
        pending = task['pending_review']
        if pending.get('stop_diagnostic'):
            _stop(engine, task, pending['stop_diagnostic']['reason'])
        if repeated_reads(pending) >= 3:
            _stop(engine, task, 'repeated_evidence')
        from .branch_review_recovery import invalid_attempts
        if invalid_attempts(task, pending) >= 3:
            _stop(engine, task, 'invalid_decision')
        disagreement.ensure_available(task, current['id'], baseline=pending.get('unsupported_baseline', 0))
        runtime.guard()
        from .provider_recovery import review_turns
        turns = review_turns(task, pending)
        if not developing(task) and not measuring(task) and turns >= max_rounds:
            _stop(engine, task, 'request_limit')
        needs_decision = bool(pending.get('require_decision')) or any(count >= 3 for count in pending.get('observations', {}).values())
        deciding = ((not developing(task) and not measuring(task) and turns >= max_rounds - 1)
                    or (developing(task) and turns >= 12)
                    or needs_decision)
        if deciding:
            _coach(engine, task, messages, 'request_limit' if turns >= max_rounds - 1 else 'missing_decision')
        # Uncapped work permits useful investigation; it does not disable the
        # decision nudge. Keep all read tools available for genuinely new evidence.
        reassessing = measuring(task) and max(turns, rounds - 1) >= max_rounds - 1 and not deciding
        if reassessing:
            _coach(engine, task, messages, 'request_limit')
        from .context_evidence import review_inventories
        messages = review_inventories(task, messages)
        # Decision coaching must not revoke the tool needed to repair citations
        # in evidence already gathered. This does not restart inspection or checks.
        decision_tools = {'review_decision', 'read_review_evidence', 'record_review_progress'} if proof is not None else {'review_decision'}
        offered = [t for t in tools if t['function']['name'] in decision_tools] if deciding else tools
        tool_choice = {'type': 'function', 'function': {'name': 'review_decision'}} if deciding and proof is None else None
        save_history(pending, messages, task)
        messages = messages[:2] + copy.deepcopy(pending['messages'])
        if proof is not None:
            packet['review_evidence'] = review_assessment.display(proof)
        if pending.get('history_partial'):
            guidance = [g for g in run.get('guidance', []) if g.get('item_id') == item['id']]
            if guidance:
                # Current operator direction must not disappear with old tool
                # exchanges; the approved plan still defines execution authority.
                packet['operator_guidance'] = guidance[-1]['message']
        if proof is not None or pending.get('history_partial'):
            if proof is not None:
                review_progress.bind(proof, {'request': task.get('prompt'), 'directions': task.get('requests', []),
                    'guidance': [g for g in run.get('guidance', []) if g.get('item_id') == item['id']]})
                packet['review_progress'] = review_progress.display(proof)
            messages[1] = {'role': 'user', 'content': json.dumps(packet)}
        request_messages = messages
        if pending.get('history_references'):
            request_messages = request_messages + [{'role': 'user', 'content': json.dumps({
                'retained_review_history': pending['history_references']})}]
        if reassessing:
            coaching = pending['coaching']['content']
            request_messages = [m for m in request_messages if m.get('content') != coaching]
            request_messages = request_messages + [{'role': 'user', 'content': coaching}]
        if deciding:
            request_messages = request_messages + [{'role':'user','content':
                instruction_prompt('review_decision_coaching')}]
        engine.store.save(task)
        engine.event(task,'review_request','Requesting item review',{'item_id':item['id'],'candidate_id':current['id']})
        try:
            if tool_choice:
                message = engine.request(runtime, request_messages, offered, 'reviewer', tool_choice=tool_choice)
            else:
                message = engine.request(runtime, request_messages, offered, 'reviewer')
        except TypeError:
            message = engine.request(runtime, request_messages, offered, 'reviewer')
        task['review_count'] += 1
        messages.append(message)
        calls = message.get('tool_calls', [])
        if not calls and message.get('content'):
            parsed = extract_embedded_decision(message['content'], current['id'], criteria)
            if parsed:
                calls = [{'id': 'call_embedded', 'type': 'function', 'function': {'name': 'review_decision', 'arguments': json.dumps(parsed)}}]
        if len(calls) > 8:
            raise ProgressPause('Reviewer exceeded the bounded tool-call allowance.')
        if not calls:
            pending['require_decision'] = True
            assessment_field = 'review_assessment' if proof is not None else 'criteria_outcomes'
            messages.append({'role':'user','content':f'Use review_decision with candidate_id "{current["id"]}" and {assessment_field} for every criterion when approving. Inspect evidence still needed for the decision; do not repeat unchanged reads or substitute conversational text for a decision.'})
        else:
            pending.pop('require_decision', None)
        # Validate the entire batch before accepting a decision or performing a
        # read. Malformed JSON is reviewer feedback, not an operator correction.
        # In particular, a valid approval beside a broken read cannot bypass it.
        try:
            parsed_calls = [engine.parse_call(call) for call in calls]
        except ToolArgumentsError as error:
            result = disagreement.unsupported(engine, task, current['id'],
                {'tool': error.name, 'executed': False}, error)
            result.update(code=error.code, executed=False,
                next_action='No calls in this batch were executed. Correct the JSON arguments using the offered tool schema, '
                            'then continue this review with the saved evidence. Do not edit code to repair a response format error.')
            for call in calls:
                messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(result)})
            save_history(pending, messages, task)
            engine.store.save(task)
            continue  # Existing durable invalid-attempt recovery chooses the next strategy.
        observations = []
        for call, (name, params) in zip(calls, parsed_calls):
            if runtime.stop.is_set(): raise InterruptedError('Task stopped')
            from .metrics import tool_action
            if name == 'review_decision':
                tool_action(task)
            if name == 'review_decision':
                try:
                    choice = disagreement.decision(params, takeover=True)
                    params['decision'] = choice
                except ValueError as error:
                    result = disagreement.unsupported(engine, task, current['id'], params, error)
                    messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result)})
                    continue
                if choice == 'APPROVE':
                    draft = pr_description.clean(params.pop('pull_request', None))
                    if draft and pr_description.enabled(task):
                        params['pull_request'] = draft
                    try:
                        if proof is not None:
                            review_progress.bind(proof, {'request': task.get('prompt'), 'directions': task.get('requests', []),
                                'guidance': [g for g in run.get('guidance', []) if g.get('item_id') == item['id']]})
                            review_progress.complete(proof, params)
                            review_assessment.validate(proof, params)
                            params.setdefault('criteria_outcomes', {
                                key: {'passed': True, 'evidence': value['reason']}
                                for key, value in params['review_assessment']['criteria'].items()})
                        # Coverage is controller-owned, never supplied by a model.
                        params.pop('packet_coverage', None)
                        if packet_coverage is not None:
                            params['packet_coverage'] = copy.deepcopy(packet_coverage)
                        branch_integration_review.bind(params, review_basis_packet, current)
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
                        engine.event(task,'review','Independent item review passed',{'item_id':item['id'],'candidate_id':current['id'],'decision':'APPROVE','feedback':review_assessment.visible_feedback(params)})
                        return {'decision':'APPROVE','feedback':item['outcome_summary']}
                elif choice in {'REQUEST_CHANGES', 'REQUEST_TESTS', 'TAKE_OVER'} and isinstance(params.get('feedback'),str):
                    try:
                        if params.get('candidate_id') != current['id']:
                            raise ValueError('Review disagreement belongs to a stale candidate.')
                        if choice == 'REQUEST_CHANGES':
                            params['defects'] = disagreement.validate(params, defect_criteria)
                            # A reviewer read tool cannot silently change the reviewed inputs.
                            if evidence.candidate(task, ctx, specs, criteria) != current:
                                raise ValueError('Candidate changed during review disagreement.')
                    except ValueError as error:
                        result = disagreement.unsupported(engine, task, current['id'], params, error)
                    else:
                        task.pop('pending_review',None)
                        task['status'] = 'running' if choice in {'REQUEST_CHANGES', 'REQUEST_TESTS'} else 'takeover_requested'
                        branch_runs.transition_item(run, item['id'], 'working')
                        result = disagreement.repair(params, current['id'], checks) if choice == 'REQUEST_CHANGES' else {'decision': choice, 'feedback': params['feedback'][:4000], 'candidate_id': current['id']}
                        if choice == 'REQUEST_CHANGES':
                            result['source_patch']=current['patch']
                            refs=item.get('review_repair',{}).get('requirement_refs')
                            if refs:result['requirement_refs']=copy.deepcopy(refs)
                            disagreement.attach(task, item, result)
                            engine.event(task,'repair_attempt','Preparing focused item repair',{'item_id':item['id'],'candidate_id':current['id'],'finding_ids':item['review_repair']['finding_ids']})
                        elif choice == 'REQUEST_TESTS':
                            item['test_expansion'] = {'candidate_id': current['id'], 'feedback': params['feedback'][:4000], 'mandated_tests': params.get('mandated_tests') or params.get('test_cases') or []}
                            task['checkpoints'].append({'number':len(task['checkpoints'])+1,'decision':'REQUEST_TESTS','feedback':params['feedback'][:4000], 'diff':current['patch'],'branch_candidate_id':current['id']})
                        engine.event(task,'review','Actionable item review claim' if choice == 'REQUEST_CHANGES' else 'Reviewer requested test expansion' if choice == 'REQUEST_TESTS' else 'Item needs takeover',
                                     {'item_id':item['id'],'decision':choice,'feedback':params['feedback'][:4000],
                                      'defects':params.get('defects'), 'candidate_id':current['id']})
                        engine.store.save(task)
                        return result
                else: result = {'error':'Return a valid independent review decision.'}
            elif name == 'record_review_progress' and proof is not None:
                try:
                    if evidence.candidate(task, ctx, specs, criteria) != current:
                        raise ValueError('Candidate changed during review. No assessment was recorded.')
                    result = review_progress.record(proof, **params)
                except (ValueError, TypeError) as error:
                    result = disagreement.unsupported(engine, task, current['id'], params, error)
                    result['review_progress'] = review_progress.display(proof)
                    result['next_action'] = 'Correct this target using its current evidence; valid recorded assessments remain saved. No approval was granted.'
                else:
                    engine.event(task, 'review_progress', 'Recorded review assessment', {
                        'item_id': item['id'], 'candidate_id': current['id'], 'target': result['recorded'],
                        'remaining': len(result['review_progress']['remaining']), 'approved': False})
            elif name == 'read_review_evidence' and proof is not None:
                try: result = review_assessment.read(proof, **params)
                except (ValueError, TypeError) as error: result = {'error': str(error)}
            elif name in {'read_file','outline_file','get_project_context','search','list_files','get_diff','read_check_output','read_merge_context','read_context_evidence','read_edit_history','inspect_image','read_browser_evidence'}:
                try: result = engine.file_tool(task,name,params,runtime=runtime)
                except (ValueError,OSError,TypeError,UnicodeError) as error: result = {'error':str(error)[:1000]}
            elif name == 'read_url': result = engine.read_url(runtime,params)
            else: result = {'error':'Review tools are read-only.'}
            if proof is not None:
                result = review_assessment.observation(proof, name, params, result)
            messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result)})
            observations.append({'name':name,'parameters':params,'result':result})
        # Measurement removes cumulative request caps, not endless identical
        # reads or invalid decisions. Keep this evidence with the candidate so
        # restarting or resuming cannot renew the same unsuccessful attempts.
        fingerprint = hashlib.sha256(json.dumps(observations,sort_keys=True).encode()).hexdigest()
        repeated = task['pending_review'].setdefault('observations',{})
        repeated[fingerprint] = repeated.get(fingerprint,0) + 1
        record_reads(pending, observations)
        save_history(task['pending_review'], messages, task)
        engine.store.save(task)
        invalid = invalid_attempts(task, task['pending_review'])
        repeated_reason = ('repeated_tool_error' if any(isinstance(o['result'],dict) and o['result'].get('error') for o in observations)
                           else 'repeated_evidence' if observations else 'missing_decision')
        if invalid >= 3:
            _stop(engine, task, 'invalid_decision')
        if repeated_reads(pending) >= 3:
            _stop(engine, task, repeated_reason)
        if invalid >= 2 or repeated_reads(pending) >= 2 or rounds == max_rounds - 1:
            _coach(engine, task, messages, 'invalid_decision' if invalid >= 2 else
                   repeated_reason if repeated_reads(pending) >= 2 else 'request_limit')
    _stop(engine, task, 'request_limit')
