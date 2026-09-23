"""Exhaustive, bounded final branch review and read-only readiness validation."""
from .instructions.runtime import text as instruction, prompt as instruction_prompt
import copy
import hashlib
import json
import shlex
import time

from . import branch_evidence as evidence, branch_workspace as work, branch_runs, branch_disagreement as disagreement
from .workspace import Workspace, git
from .unattended_items import completion_order
from .providers import ProviderError
from . import review_context, review_disputes
from . import branch_final_recovery as recovery

CHUNK_SIZE = 20000
MAX_CONTENT = 1000000


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def requirement_projection(run, requirements):
    """Original scope is reviewable; completed repairs are historical evidence."""
    amendments=[a for revision in run.get('operator_revision_history', [])
                for a in revision.get('amendments', [])] + run.get('amendments', [])
    repairs={a['item']['id']:a['item'] for a in amendments}
    active=[];historical=[]
    for row in requirements:
        repair=repairs.get(row['item_id'])
        # Conflict resolution and model changes reauthorize the plan and move
        # old amendments into history. Keep unchanged repair notes historical;
        # explicitly revised operator instructions remain current scope.
        is_history=repair and all(row[k]==repair.get(k) for k in ('title','instructions')) and row['criterion'] in repair['acceptance_criteria']
        (historical if is_history else active).append(row)
    # Original receipt outcomes concern earlier candidates. Keep them in the
    # bound manifest, available by reference, not mixed into current criteria.
    current=[{k:r[k] for k in ('id','item_id','title','instructions','criterion')} for r in active]
    return active,historical,current


def build_manifest(run, *, version=2):
    if version not in (1, 2):raise ValueError('Unsupported final manifest version')
    branch_runs.require_supported(run)
    if not run.get('items') or any(i['status'] not in branch_runs.DONE for i in run['items']) or run.get('pending_operations') or run.get('target_update'):
        raise ValueError('Finish every item and pending commit before final review')
    mapping = run['workspace_mapping']; source = mapping['source']; tip = run['expected_feature_tip']
    work.validate_owned(mapping, tip)
    if Workspace(mapping['workspace']).patch(validate=True) or git(mapping['workspace'], 'status', '--porcelain').strip():
        raise ValueError('Private workspace must be clean before final review')
    if git(mapping['workspace'], 'rev-parse', 'HEAD').strip() != mapping['workspace_head']:
        raise ValueError('Private baseline changed')
    planned = {i['id']: i for i in run['plan']['items']}
    actual = {i['id']: i for i in run['items']}
    if len(actual) != len(run['items']) or not set(planned).issubset(actual):
        raise ValueError('Accepted plan items are missing or duplicated')
    for key, item in planned.items():
        if any(actual[key].get(field) != item.get(field) for field in ('title', 'instructions', 'acceptance_criteria', 'required_checks', 'dependencies')):
            raise ValueError('Accepted plan requirements changed')
    previous = run['base_sha']; commits = []; requirements = []
    ordered_items = completion_order(run)
    from .branch_update import advance_receipts
    updates=copy.deepcopy(run.get('target_update_history',[]))
    private=(ordered_items[0].get('commit_receipt') or {}).get('private_old')
    for item in ordered_items:
        operation = item.get('commit_receipt') or {}
        if operation.get('old_tip')!=previous:
            previous,private=advance_receipts(run,previous,private,updates)
        if operation.get('stage') != 'completed' or operation.get('run_id') != run['id'] or operation.get('item_id') != item['id'] or operation.get('old_tip') != previous:
            raise ValueError('Missing or discontinuous item commit receipt')
        saved = json.loads(operation['receipt']); receipt_id = saved.pop('id')
        if saved['candidate']['context']['item_id'] != item['id'] or saved['candidate']['context']['run_id'] != run['id'] or operation.get('candidate_id') != saved['candidate']['id']:
            raise ValueError('Item receipt belongs to a different candidate')
        if evidence._digest(saved) != receipt_id or saved['review'].get('decision') != 'APPROVE':
            raise ValueError('Item evidence receipt is invalid')
        rebuilt = evidence.ready_receipt(saved['candidate'], saved['checks'], saved['review'], saved['worker_model'], saved['reviewer_model'], saved['criteria_outcomes'])
        if json.loads(rebuilt)['id'] != receipt_id or saved['candidate']['criteria'] != item['acceptance_criteria']:
            raise ValueError('Item acceptance evidence changed')
        new_tip = operation['new_tip']
        if item['status'] == 'committed':
            parents = work.source_git(source, 'rev-list', '--parents', '-n', '1', new_tip).split()
            if parents != [new_tip, previous] or new_tip == previous:
                raise ValueError('Feature commit ancestry differs from the receipts')
        elif new_tip != previous or saved['outcome'] != 'satisfied_without_change':
            raise ValueError('No-change outcome does not match its receipt')
        if work.source_git(source, 'rev-parse', new_tip + '^{tree}') != operation['tree']:
            raise ValueError('Feature tree differs from its commit receipt')
        previous = new_tip
        private=operation['private_new']
        commits.append({'item_id': item['id'], 'old_tip': operation['old_tip'], 'new_tip': new_tip,
                        'tree': operation['tree'], 'receipt_id': receipt_id, 'outcome': item['status'],
                        'files': [name.decode() for name in work.source_git(source, 'diff', '--name-only', '-z', operation['old_tip'], new_tip, '--', binary=True).split(b'\0') if name]})
        for index, criterion in enumerate(item['acceptance_criteria']):
            requirements.append({'id': '%s:%s' % (item['id'], index + 1), 'item_id': item['id'], 'title': item['title'],
                                 'instructions': item['instructions'], 'criterion': criterion,
                                 'outcome': saved['criteria_outcomes'][criterion], 'review': saved['review'],
                                 'check_evidence': saved['checks'], 'commit': new_tip, 'receipt_id': receipt_id})
    previous,private=advance_receipts(run,previous,private,updates)
    if updates: raise ValueError('Discontinuous branch update receipts')
    if private != mapping['workspace_head']:
        raise ValueError('Private baseline does not match the final item receipt')
    if previous != tip:
        raise ValueError('Feature tip includes work outside the accepted item receipts')
    # advance_receipts above has validated the entire update ancestry. Review
    # only what this branch adds to its latest incorporated target; keep the
    # original base and item receipts for the full historical audit.
    review_base = (run.get('target_update_history') or [{}])[-1].get('target_tip', run['base_sha'])
    diff = work.source_git(source, 'diff', '--binary', '--no-ext-diff', '--no-textconv', review_base, tip, '--')
    names = work.source_git(source, 'diff', '--name-status', '-z', '--no-renames', review_base, tip, '--', binary=True).split(b'\0')
    files = [{'status': names[n].decode(), 'path': names[n+1].decode()} for n in range(0, len(names)-1, 2)]
    stats = work.source_git(source, 'diff', '--numstat', '-z', '--no-renames', review_base, tip, '--', binary=True)
    counts = {}
    for row in stats.split(b'\0'):
        if row:
            added, removed, name = row.split(b'\t', 2)
            counts[name.decode()] = {'added_lines': int(added) if added != b'-' else None,
                                     'removed_lines': int(removed) if removed != b'-' else None}
    for file in files:
        file.update(counts[file['path']])
        file['item_ids'] = [c['item_id'] for c in commits if file['path'] in c['files']]
    historical=[];current=requirements
    if version==2:
        requirements,historical,current=requirement_projection(run,requirements)
    # Current criteria and the complete diff are reviewed exhaustively. Full
    # receipts remain hash-bound and retrievable as historical evidence.
    streams = [('requirements', _json(current)), ('diff', diff)]
    chunks = []
    for kind, content in streams:
        for index,text in enumerate(review_context.chunks(content,CHUNK_SIZE),1):
            chunks.append({'id': '%s:%s' % (kind, index), 'kind': kind,
                           'digest': hashlib.sha256(text.encode()).hexdigest(), 'content': text})
    result = {'version': version, 'run_id': run['id'], 'plan_revision': run['plan_revision'],
              'plan_digest': run['plan_digest'], 'plan_content_digest': _hash(run['plan']),
              'base_sha': run['base_sha'], 'review_base_sha': review_base, 'feature_ref': run['feature_ref'], 'feature_tip': tip,
              'feature_tree': work.source_git(source, 'rev-parse', tip + '^{tree}'),
              'target_ref': run['target_ref'], 'target_tip': work._tip(source, run['target_ref']),
              'files': files, 'commits': commits, 'requirements': requirements, 'chunks': chunks,
              'diff': diff, 'diff_bytes': len(diff.encode()), 'diff_lines': len(diff.splitlines())}
    if version==2:result['repair_evidence']=historical
    result['id'] = _hash(result)
    return result


def check_sources(packet):
    """Retained-log access follows controller-bound checks, never a model's ID."""
    sources = copy.deepcopy(packet.get('check_output_sources', []))
    for bound in packet.get('checks') or packet.get('review_context', {}).get('final_checks', []):
        record = bound.get('record', bound)
        if not bound.get('candidate_id') or not record.get('run_id'):
            continue
        sources.append({'candidate_id': bound['candidate_id'], 'run_id': record['run_id'],
                        'record_digest': evidence._digest(record) if 'record' in bound else bound.get('record_digest')})
    return sources


def read_check_output(engine, task, sources, args):
    from . import check_output
    if set(args) - {'run_id', 'offset'} or not isinstance(args.get('run_id'), str):
        raise ValueError('Use run_id and optional offset from this packet\'s check evidence.')
    grant = next((s for s in sources if s['run_id'] == args['run_id']), None)
    record = next((r for r in reversed(task.get('checks', [])) if r.get('run_id') == args['run_id']), None)
    if not grant or not record or evidence._digest(record) != grant['record_digest']:
        raise ValueError('This run is not a bound check of the current review packet. Use its check_output_sources or read_review_evidence(source="checks").')
    try:
        result = check_output.read(engine.store, task['id'], **args)
    except ValueError as error:
        return {'run_id': args['run_id'], 'available': False, 'error': str(error),
                'guidance': 'The saved check preview remains in the review evidence. Assess what it establishes and disclose any missing verification; unavailable raw output is not new proof or a reason to repeat this read.'}
    return {**result, 'candidate_id': grant['candidate_id']}


def review_paged(engine, runtime, manifest, packet, chunk_ids, criterion_ids):
    encoded = _json(packet)
    if len(encoded) <= 60000:
        return _review(engine, runtime, manifest, packet, chunk_ids, criterion_ids)
    pages = review_context.chunks(encoded, CHUNK_SIZE)
    coverage = []
    packet_digest = _hash(packet)
    for index, content in enumerate(pages):
        page = {'packet_digest': packet_digest, 'page_index': index, 'page_total': len(pages),
                'check_output_sources': check_sources(packet),
                'content': content, 'instruction': 'Review this ordered evidence page. It may begin or end mid-record. This is partial evidence, not task completion. Report concrete defects; synthesis follows only after every page is independently approved.'}
        result = _review(engine, runtime, manifest, page, [], [])
        if result['decision'] != 'APPROVE': return result
        coverage.append({'page':index,'digest':_hash(content),'decision':result['decision'], 'review': result})
    from .context_evidence import retain
    reference = retain(runtime.task, packet, 'final_review_packet')
    summary = {'packet_digest':packet_digest, 'complete_packet_reference':reference,
               'check_output_sources': check_sources(packet),
               'page_coverage':[{k:v for k,v in row.items() if k != 'review'} for row in coverage], 'coverage':coverage,
               'chunk_ids':chunk_ids,'criteria_ids':criterion_ids,
               'instruction':'Every ordered evidence page above has an independent approval saved against this candidate. Synthesize their complete coverage; never treat missing or rejected pages as approval.'}
    return _review(engine, runtime, manifest, summary, chunk_ids, criterion_ids, check_packet=packet)


def _review(engine, runtime, manifest, packet, chunk_ids, criterion_ids, *, context_reader=None, progress=None, check_packet=None):
    from .engine import tool, ToolArgumentsError
    from . import pr_description, review_assessment
    packet = copy.deepcopy(packet)
    packet['check_output_sources'] = check_sources(packet)
    proof = None
    if review_assessment.enabled(runtime.task):
        scope = _hash({'manifest_id': manifest['id'], 'chunk_ids': chunk_ids, 'criteria_ids': criterion_ids, 'page': packet.get('page_index')})
        proof = review_assessment.prepare(scope, packet, criterion_ids, partial=not criterion_ids)
        if check_packet is not None:
            review_assessment.refresh_check_claims(proof, check_packet)
        packet = copy.deepcopy(packet)
        packet['original_request'] = review_assessment.original_request(runtime.task)
        packet['review_evidence'] = review_assessment.display(proof)
    chunk_prop = {'type': 'array', 'items': {'type': 'string'}, 'description': f"Must be exact chunk_ids: {json.dumps(chunk_ids)}"}
    if chunk_ids: chunk_prop['enum'] = [chunk_ids]
    else: chunk_prop['maxItems'] = 0
    criteria_prop = {'type': 'array', 'items': {'type': 'string'}, 'description': f"Must be exact criteria_ids: {json.dumps(criterion_ids)}"}
    if criterion_ids: criteria_prop['enum'] = [criterion_ids]
    else: criteria_prop['maxItems'] = 0
    tools = [tool('final_review_decision', 'Review this exact final packet; missing coverage cannot approve.',
                  {'decision': {'type': 'string', 'enum': ['APPROVE', 'REQUEST_CHANGES']},
                   'manifest_id': {'type': 'string', 'enum':[manifest['id']], 'description': f"Must be exact manifest_id: {manifest['id']}"},
                   'chunk_ids': chunk_prop,
                   'criteria_ids': criteria_prop,
                   'feedback': {'type': 'string', 'description': 'Nonempty string of at most 4000 characters summarizing your evaluation.'}, 'defects': disagreement.schema([r['id'] for r in manifest.get('requirements', []) if isinstance(r, dict) and 'id' in r] or None)},
                  ['decision', 'manifest_id', 'chunk_ids', 'criteria_ids', 'feedback'])]
    tools[0]['function']['parameters']['properties']['suggestions']={'type':'array','maxItems':8,'items':{'type':'string'}}
    publication = bool(criterion_ids) and pr_description.enabled(runtime.task)
    if publication:
        tools[0]['function']['parameters']['properties']['pull_request'] = pr_description.SCHEMA
    tools.append(tool('read_final_context','Read up to 200 numbered lines from this exact candidate; larger ranges return a page with next_start_line. Never approval or coverage.', {'manifest_id':{'type':'string','enum':[manifest['id']]},'path':{'type':'string'},'start_line':{'type':'integer','minimum':1},'end_line':{'type':'integer','minimum':1}}, ['manifest_id','path','start_line']))
    tools.append(tool('report_review_context_blocker','Pause when necessary candidate context is unavailable; this is never approval.',{'manifest_id':{'type':'string','enum':[manifest['id']]},'path':{'type':'string'}},['manifest_id','path']))
    if runtime.task['branch_run'].get('conflict_resolution'):
        from .engine import READ_TOOLS
        tools.extend(t for t in READ_TOOLS if t['function']['name']=='read_merge_context')
    from .engine import READ_TOOLS
    tools.extend(t for t in READ_TOOLS if t['function']['name'] == 'read_context_evidence')
    tools.append(tool('read_check_output',
        'Read retained output for a check in this packet\'s check_output_sources. Use the saved output preview first; read missing details with run_id and offset (8000 bytes per page). Read-only; does not rerun checks or approve the work.',
        {'run_id': {'type': 'string'}, 'offset': {'type': 'integer', 'minimum': 0}}, ['run_id']))
    if proof is not None:
        tools.extend(t for t in READ_TOOLS if t['function']['name'] == 'inspect_image')
        tools = review_assessment.tools_with_contract(tools, proof, 'final_review_decision')
    encoded = _json(review_assessment.packet_for_model(packet) if proof is not None else packet)
    if len(encoded) > 60000:
        if proof is None:
            raise ValueError('Final review packet exceeds 60,000 characters; nothing was omitted')
        from .context_evidence import retain
        encoded = _json({'complete_packet_reference': retain(runtime.task, packet, 'final_review_packet'),
                         'manifest_id': manifest['id'], 'chunk_ids': chunk_ids, 'criteria_ids': criterion_ids,
                         'instruction': 'Read the full packet and its evidence source IDs with read_context_evidence before deciding. No evidence was discarded; this envelope is not evidence of completion.'})
    coverage_instruction = f" Finish review with final_review_decision after inspecting the evidence, using exact coverage arguments: decision matching the evidence ('APPROVE' or 'REQUEST_CHANGES'), manifest_id={json.dumps(manifest['id'])}, chunk_ids={json.dumps(chunk_ids)}, criteria_ids={json.dumps(criterion_ids)}, and a nonempty feedback string summarizing your decision with concrete reasons for the selected decision."
    messages = [{'role': 'system', 'content': instruction_prompt("final_review") + instruction('reviewer.final_context') + coverage_instruction + disagreement.REVIEW_INSTRUCTION},
                {'role': 'user', 'content': encoded}]
    if proof is not None:
        messages[0]['content'] += '\n' + review_assessment.INSTRUCTION
    if publication:
        messages[0]['content'] += pr_description.FINAL
    messages[0]['content'] += ' ' + review_context.PATH_GUIDANCE + instruction('reviewer.original_scope')
    direction=runtime.task.get('steer_guidance') or next((g.get('message') for g in reversed(runtime.task['branch_run'].get('guidance',[])) if g.get('message')),None)
    if direction:
        messages.append({'role':'user','content':'Latest operator direction for this review: '+direction[:8000]+'\nAssess it against the approved requirements and actual evidence. It is not approval, new check permission, or permission to skip independent review.'})
    attempts = runtime.task['branch_run'].setdefault('final_review_corrections', {})
    identity = {'manifest_id':manifest['id'],'chunk_ids':chunk_ids,'criteria_ids':criterion_ids}
    if 'page_index' in packet:
        identity.update(packet_digest=packet['packet_digest'], page_index=packet['page_index'])
    key = _hash(identity)
    state=recovery.begin(runtime.task,manifest,key,packet,messages)
    if proof is not None:
        proof = state.setdefault('evidence_review', proof)
        review_assessment.refresh_check_claims(proof, check_packet if check_packet is not None else packet)
    recovery.guard(runtime)
    cached=state.get('result')
    if cached and state.get('result_digest')==_hash(cached):
        expected={'manifest_id':manifest['id'],'chunk_ids':chunk_ids,'criteria_ids':criterion_ids}
        if all(cached.get(k)==v for k,v in expected.items()):
            disagreement.decision(cached)
            if cached['decision']=='REQUEST_CHANGES':disagreement.validate(cached,[r['id'] for r in manifest['requirements']])
            _independent(runtime.task,cached.get('reviewer_model'))
            if proof is not None and cached['decision'] == 'APPROVE':
                review_assessment.retained(cached, proof['scope'])
            return copy.deepcopy(cached)
    messages.extend(copy.deepcopy(state.get('messages',[])))
    packet['context_references']=copy.deepcopy(state.get('context_references',[]))
    # Display metadata stays outside packet bindings so a label change cannot
    # invalidate already reviewed evidence during continuation.
    scope = progress if progress is not None else packet.get('scope', {})
    display = {k: scope[k] for k in ('chunk_index', 'chunk_total') if k in scope} if not criterion_ids else {}
    engine.store.save(runtime.task)
    while True:
        recovery.guard(runtime)
        if recovery.needed(runtime.task,key,state):
            recovery.recover(engine,runtime,key,state,messages)
        label = 'item' if manifest.get('kind') == 'item' else 'final'
        engine.event(runtime.task,'review_request',f'Requesting {label} packet review',{'manifest_id':manifest['id'],'chunk_ids':chunk_ids,'stage':'synthesis' if criterion_ids else 'chunk',**display})
        message = engine.request(runtime, messages, tools, 'reviewer', purpose='branch_final', tool_choice='required')
        recovery.guard(runtime)  # A reply to superseded guidance cannot approve this packet.
        state['reviewer_model']=recovery.model(runtime.task)
        calls = message.get('tool_calls', [])
        try:
            if len(calls) != 1:
                raise ValueError('Return exactly one offered tool call: read missing evidence or submit final_review_decision.')
            name, result = engine.parse_call(calls[0])
            # Some tool-capable models emit the conventional functions.
            # namespace. Accept only an exact alias of a tool offered here;
            # coverage, defect validation and independent identity still apply.
            offered = {t['function']['name'] for t in tools}
            if name.startswith('functions.') and name[len('functions.'):] in offered:
                name = name[len('functions.'):]
                message = copy.deepcopy(message)
                calls = message['tool_calls']
                calls[0]['function']['name'] = name
            if name in {tool['function']['name'] for tool in tools}:
                from .metrics import tool_action
                tool_action(runtime.task)
            if name == 'report_review_context_blocker':
                if result.get('manifest_id')!=manifest['id'] or not any(r.get('path')==result.get('path') and r.get('available') is False for r in packet.get('context_references',[])):
                    raise ValueError('Report a context blocker only after a recorded unavailable read of this exact candidate/path.')
                from .branch_pause import PauseError
                raise PauseError('review_context_unavailable',stage='finalizing')
            if name == 'read_review_evidence' and proof is not None:
                try:
                    # The catalog grows as evidence is read; never cache a stale listing.
                    excerpt = review_assessment.read(proof, **result)
                except TypeError as error:
                    raise ValueError(str(error)) from None
                excerpt = recovery.context_read(engine, runtime, key, state,
                    {'tool': name, 'arguments': result, 'content_digest': _hash(excerpt)}, lambda: excerpt)
                messages.append(message); messages.append({'role': 'tool', 'tool_call_id': calls[0]['id'], 'content': _json(excerpt)})
                recovery.persist(engine, runtime.task, state, messages)
                continue
            if name == 'read_check_output':
                excerpt = read_check_output(engine, runtime.task, packet['check_output_sources'], result)
                excerpt = recovery.context_read(engine, runtime, key, state,
                    {'tool': name, 'arguments': result, 'content_digest': _hash(excerpt)}, lambda: excerpt)
                if proof is not None:
                    excerpt = review_assessment.observation(proof, name, result, excerpt)
                messages.append(message); messages.append({'role': 'tool', 'tool_call_id': calls[0]['id'], 'content': _json(excerpt)})
                recovery.persist(engine, runtime.task, state, messages)
                continue
            if name == 'read_final_context':
                excerpt=recovery.context_read(engine,runtime,key,state,result,
                    lambda:context_reader(result) if context_reader else review_context.read(runtime.task['branch_run'],manifest,result))
                if proof is not None:
                    excerpt = review_assessment.observation(proof, name, result, excerpt)
                messages.append(message);messages.append({'role':'tool','tool_call_id':calls[0]['id'],'content':_json(excerpt)})
                packet['context_references']=copy.deepcopy(state['context_references'])
                recovery.persist(engine,runtime.task,state,messages)
                continue
            if name == 'inspect_image' and proof is not None:
                from .vision import inspect_image_tool
                excerpt = recovery.context_read(engine, runtime, key, state, {'tool': name, 'arguments': result},
                    lambda: inspect_image_tool(engine, runtime.task, result, runtime=runtime, role='reviewer'))
                excerpt = review_assessment.observation(proof, name, result, excerpt)
                messages.append(message); messages.append({'role': 'tool', 'tool_call_id': calls[0]['id'], 'content': _json(excerpt)})
                recovery.persist(engine, runtime.task, state, messages)
                continue
            if name=='read_merge_context':
                from .branch_conflicts import read
                excerpt=recovery.context_read(engine,runtime,key,state,{'tool':name,'arguments':result},
                    lambda:read(runtime.task,**result))
                messages.append(message);messages.append({'role':'tool','tool_call_id':calls[0]['id'],'content':_json(excerpt)})
                recovery.persist(engine,runtime.task,state,messages)
                continue
            if name == 'read_context_evidence':
                from .context_evidence import read
                excerpt = recovery.context_read(engine, runtime, key, state,
                    {'tool': name, 'arguments': result}, lambda: read(runtime.task, **result))
                messages.append(message); messages.append({'role': 'tool', 'tool_call_id': calls[0]['id'], 'content': _json(excerpt)})
                recovery.persist(engine, runtime.task, state, messages)
                continue
            expected = {'manifest_id':manifest['id'],'chunk_ids':chunk_ids,'criteria_ids':criterion_ids}
            wrong = [field for field,value in expected.items() if result.get(field) != value]
            if name != 'final_review_decision':
                raise ValueError('Use final_review_decision, not another tool.')
            if wrong:
                raise ValueError('Correct these coverage fields exactly: '+_json({field:expected[field] for field in wrong}))
            if not isinstance(result.get('feedback'),str) or not result['feedback'].strip() or len(result['feedback']) > 4000:
                raise ValueError('feedback must be a nonempty string of at most 4000 characters.')
            result['decision'] = disagreement.decision(result)
            if proof is not None:
                review_assessment.validate(proof, result)
            if result['decision'] == 'REQUEST_CHANGES':
                try:
                    result['defects'] = disagreement.validate(result, [r['id'] for r in manifest['requirements']])
                except ValueError as error:
                    disagreement.unsupported(engine, runtime.task, key, result, error)
                    raise
        except (ValueError, ToolArgumentsError) as error:
            if getattr(error,'pause_cause',None):raise
            attempts[key] = attempts.get(key,0) + 1
            feedback = {'error':str(error),'attempt':attempts[key], **getattr(error, 'correction', {})}
            engine.event(runtime.task,'review_feedback','Final review response needs correction',feedback)
            engine.store.save(runtime.task)
            if calls and all(isinstance(call,dict) and isinstance(call.get('id'),str) and call['id'] for call in calls):
                messages.append(message)
                for call in calls:
                    messages.append({'role':'tool','tool_call_id':call['id'],'content':_json(feedback)})
            else:
                messages.append({'role':'user','content':_json(feedback)})
            recovery.persist(engine,runtime.task,state,messages)
            continue
        draft = pr_description.clean(result.pop('pull_request', None))
        if publication and result['decision'] == 'APPROVE' and draft:
            result['pull_request'] = draft
        if packet.get('context_references'):result['context_references']=copy.deepcopy(packet['context_references'])
        if state.get('reviewer_model'):result['reviewer_model']=state['reviewer_model']
        _independent(runtime.task,result.get('reviewer_model'))
        state['result']=copy.deepcopy(result);state['result_digest']=_hash(result)
        state.pop('evidence_review', None)
        recovery.persist(engine,runtime.task,state,messages)
        title = (f"{label.capitalize()} review chunk {display['chunk_index']} of {display['chunk_total']} completed"
                 if 'chunk_index' in display and 'chunk_total' in display
                 else f'{label.capitalize()} packet review completed')
        engine.event(runtime.task,'review',title,{'decision':result['decision'],'feedback':review_assessment.visible_feedback(result),'manifest_id':manifest['id'],'chunk_ids':chunk_ids,'defects':result.get('defects'),**display})
        return result


def _independent(task, reviewer):
    worker=task.get('providers',{}).get('worker')
    if worker and reviewer and evidence.model_identity(worker)==evidence.model_identity(reviewer):
        raise ValueError('Final reviewer is not independent')


def final_check_review(engine, runtime):
    from . import branch_review_reuse
    task = runtime.task; run = task['branch_run']; manifest = build_manifest(run)
    review_inputs = branch_review_reuse.input_digest(task)
    worker = evidence.model_identity(task['providers']['worker']); reviewer = evidence.model_identity(task['providers']['reviewer'])
    if worker == reviewer:
        raise ValueError('Final review requires an independent model')
    specifications = run['plan']['final_checks']
    if not specifications:
        raise ValueError('Final integration checks are required')
    from .test_policy import is_plan_preview, is_git_command
    if any(is_plan_preview(s) or is_git_command(s) for s in specifications):
        real_specs = [s for s in specifications if not is_plan_preview(s) and not is_git_command(s)]
        if real_specs:
            specifications = real_specs
            run['plan']['final_checks'] = real_specs
    criteria = [r['id'] for r in manifest['requirements']]
    context = {'run_id': run['id'], 'plan_revision': run['plan_revision'], 'item_id': 'final', 'item_revision': 1,
               'feature_parent': run['expected_feature_tip']}
    current = evidence.candidate(task, context, specifications, criteria)
    for expected in current['checks']:
        try:
            existing = next((c for c in reversed(task['checks']) if evidence.same(c, expected)), {})
            evidence.bind_check(current, expected['command'], existing, expected.get('directory', '.'))
        except ValueError:
            result = engine.checks(runtime, shlex.join(expected['command']), directory=expected.get('directory', '.'))
            if not result.get('passed'):
                return {'decision': 'REQUEST_CHANGES', 'feedback': 'Repair the failing final integration check.', 'checks': result}
    checks = evidence.current_checks(current, task['checks'])
    reused = branch_review_reuse.finalize(engine, runtime, manifest, current, checks)
    if reused is not None:
        return reused
    from .context_evidence import retain
    history=retain(task,{'role':'historical_evidence_not_requirements',
        'original_item_evidence':manifest['requirements'],
        'repair_item_evidence':manifest.get('repair_evidence',[])},'final_review_history')
    # Keep complete historical receipts available without turning each repair
    # into another set of requirements for the reviewer to "fix" recursively.
    review_context = {
        'historical_evidence_reference':history,
        'history_rule':'Use read_context_evidence to inspect full earlier receipts if needed. Historical assertions are not current requirements; inspect the current candidate and final checks.',
        'repair_history': [{ 'item_id':i['id'], 'candidate_id':i['review_repair'].get('candidate_id'),'finding_ids':i['review_repair'].get('finding_ids',[]),'dispositions':i['review_repair'].get('dispositions',[]),'prior_counterevidence':i['review_repair'].get('prior_counterevidence',[])} for i in run['items'] if i.get('review_repair')][-3:],
        'acceptance_criteria': [{'id': r['id'], 'criterion': r['criterion']} for r in manifest['requirements']],
        'final_checks': [{'candidate_id': bound['candidate_id'], 'command': bound['command'],
                          **({'directory': bound['directory']} if 'directory' in bound else {}),
                          'passed': bound['record']['passed'], 'exit_code': bound['record']['exit_code'],
                          'verification_identity': bound['record']['verification_identity'],
                          'input_identity': bound['record']['input_identity'],
                          **{key: copy.deepcopy(bound['record'][key]) for key in
                             ('run_id', 'output', 'truncated', 'raw_output') if key in bound['record']},
                          'record_digest': evidence._digest(bound['record'])} for bound in checks],
    }
    reviews = []
    for index, chunk in enumerate(manifest['chunks'], 1):
        packet = {'manifest_id': manifest['id'], 'chunk_ids': [chunk['id']], 'criteria_ids': [], 'chunk': chunk, 'review_context': review_context, 'location_index':manifest['files'],
                  'scope': {'kind': chunk['kind'], 'chunk_index': index, 'chunk_total': len(manifest['chunks']),
                            'context_role': 'global_background', 'criterion_completion_required': False},
                  'instruction': 'Review only the supplied chunk_ids; criteria_ids is empty for this chunk review. '
                                 'review_context is global background, not coverage required in this chunk. '
                                 'Serialized receipts and diffs are intentionally split and may begin or end mid-record or mid-hunk. '
                                 'Do not reject solely because a criterion, receipt, or related evidence is absent here or continues in another chunk. '
                                 'Report concrete defects supported by this chunk; do not assume missing context proves a defect. '
                                 'Final synthesis receives all chunk reviews and must verify every criterion before completion.'}
        review = review_paged(engine, runtime, manifest, packet, [chunk['id']], [])
        if review['decision'] != 'APPROVE':
            chunk_manifest = build_manifest(run)
            if dict(chunk_manifest, target_tip=manifest['target_tip']) != dict(manifest, target_tip=manifest['target_tip']) or evidence.candidate(task, context, specifications, criteria) != current:
                from .branch_pause import PauseError
                raise PauseError('branch_drift', stage='finalizing')
            return disagreement.repair({**review,'source_patch':manifest['diff']}, current['id'], checks)
        reviews.append(review)
    chunks = [c['id'] for c in manifest['chunks']]
    packet = {'manifest_id': manifest['id'], 'chunk_ids': chunks, 'criteria_ids': criteria,
              'coverage': [{'chunk_id': c['id'], 'digest': c['digest'], 'review': r} for c, r in zip(manifest['chunks'], reviews)],
              'requirements': [{'id': r['id'], 'criterion': r['criterion'], 'item_id': r['item_id']} for r in manifest['requirements']],
              'historical_evidence_reference':history,
              'checks': checks, 'instruction': 'Synthesize all approved chunk reviews against every criterion and final check.'}
    from . import pr_description
    if pr_description.enabled(task):
        packet['publication_drafts'] = pr_description.item_drafts(manifest)
    overall = review_paged(engine, runtime, manifest, packet, chunks, criteria)
    current_manifest = build_manifest(run)
    manifest_match = dict(current_manifest, target_tip=manifest['target_tip']) == dict(manifest, target_tip=manifest['target_tip'])
    if overall['decision'] != 'APPROVE':
        if not manifest_match or evidence.candidate(task, context, specifications, criteria) != current:
            from .branch_pause import PauseError
            raise PauseError('branch_drift', stage='finalizing')
        return disagreement.repair({**overall,'source_patch':manifest['diff']}, current['id'], checks)
    with engine.lock:
        recovery.guard(runtime)
        if (not manifest_match or evidence.candidate(task, context, specifications, criteria) != current
                or branch_review_reuse.input_digest(task) != review_inputs):
            from .branch_pause import PauseError
            raise PauseError('branch_drift', stage='finalizing')
    blocker = None
    try: work.source_git(run['workspace_mapping']['source'], 'merge-base', '--is-ancestor', current_manifest['target_tip'], manifest['feature_tip'])
    except ValueError: blocker = 'The target branch has new commits. Choose Update branch & recheck to combine them with the saved task before merging.'
    readiness = {'version': 1, 'manifest': current_manifest, 'candidate': current, 'checks': checks, 'reviews': reviews,
                 'review': overall, 'worker_model': worker, 'reviewer_model': overall.get('reviewer_model',recovery.model(task)), 'integration_blocker': blocker,
                 'review_input_digest': review_inputs}
    readiness['id'] = _hash(readiness)
    return {'decision': 'APPROVE', 'readiness': readiness}


def validate_record(readiness, task, seen=None):
    """Validate immutable approval/check receipts without requiring an old checkout."""
    saved = copy.deepcopy(readiness); identity = saved.pop('id', None)
    if identity != _hash(saved): raise ValueError('Final readiness receipt changed')
    current = saved['candidate']
    if len(current['checks']) != len(saved['checks']): raise ValueError('Final check evidence is incomplete')
    for expected, bound in zip(current['checks'], saved['checks']):
        if current.get('id') and bound.get('candidate_id') != current['id']:
            raise ValueError('Final check belongs to a different candidate')
        evidence.bind_check(current, expected['command'], bound['record'], expected.get('directory', '.'))
    if saved.get('version') == 2:
        from . import branch_review_reuse
        branch_review_reuse.validate(readiness, task, seen)
        return True
    if saved.get('version', 1) != 1:
        raise ValueError('Unsupported final readiness version')
    manifest = saved['manifest']
    chunks = [c['id'] for c in manifest['chunks']]
    criteria = [r['id'] for r in manifest['requirements']]
    reviews = saved['reviews']
    if len(reviews) != len(chunks) or any(r.get('manifest_id') != manifest['id'] or r.get('decision') != 'APPROVE' or r.get('chunk_ids') != [chunk] or r.get('criteria_ids') != [] for chunk, r in zip(chunks, reviews)):
        raise ValueError('Final chunk coverage is incomplete')
    for review in reviews:
        disagreement.decision(review)
        if review.get('reviewer_model') and evidence.model_identity(review['reviewer_model'])==evidence.model_identity(saved['worker_model']):
            raise ValueError('Final chunk reviewer is not independent')
    overall = saved['review']
    disagreement.decision(overall)
    if overall.get('manifest_id') != manifest['id'] or overall.get('decision') != 'APPROVE' or overall.get('chunk_ids') != chunks or overall.get('criteria_ids') != criteria:
        raise ValueError('Final requirement coverage is incomplete')
    if evidence.model_identity(saved['worker_model']) == evidence.model_identity(saved['reviewer_model']):
        raise ValueError('Final reviewer is not independent')
    if current.get('review_contract_version') == 1:
        from .review_assessment import retained
        for review in [*reviews, overall]:
            retained(review, _hash({'manifest_id': manifest['id'], 'chunk_ids': review['chunk_ids'],
                                    'criteria_ids': review['criteria_ids'], 'page': None}))
    return True


def validate(readiness, task):
    validate_record(readiness, task)
    if readiness.get('review_input_digest'):
        from . import branch_review_reuse
        if readiness['review_input_digest'] != branch_review_reuse.input_digest(task):
            raise ValueError('Operator review directions changed')
    if build_manifest(task['branch_run'],version=readiness['manifest'].get('version',1)) != readiness['manifest']:
        raise ValueError('Final branch, target, plan or evidence changed; revalidate final readiness')
    current = readiness['candidate']
    if evidence.candidate(task, current['context'], current['check_specifications'], current['criteria']) != current:
        raise ValueError('Final verification environment or workspace changed')
    if readiness.get('reuse', {}).get('mode') == 'integration':
        from . import branch_review_reuse
        branch_review_reuse.validate_diff(readiness, task)
    return True
