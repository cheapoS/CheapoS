"""Compose prior approvals with exact integration evidence, never rewrite them."""
import copy
import hashlib
import json

from . import branch_evidence as evidence, branch_update, review_assessment
from . import branch_workspace as work


def input_digest(task):
    run = task['branch_run']
    return evidence._digest({'prompt': task.get('prompt'), 'requests': task.get('requests', []),
        'inputs': run.get('inputs', {}), 'review_contract_version': task.get('review_contract_version'),
        'direction': task.get('steer_guidance'), 'guidance': run.get('guidance', [])})


def requirements(manifest, excluding=None):
    return [{k: row[k] for k in ('id', 'item_id', 'title', 'instructions', 'criterion')}
            for row in manifest['requirements'] if row['item_id'] != excluding]


def basis_for(task, identity):
    return next((r for r in reversed(task['branch_run'].get('previous_readiness', []))
                 if isinstance(r, dict) and r.get('id') == identity), None)


def update_for(task, identity):
    op = next((r for r in task['branch_run'].get('target_update_history', []) if r.get('digest') == identity), None)
    if (not op or op.get('stage') != 'completed' or op.get('approved') is not True
            or branch_update.receipt_digest(op) != identity):
        raise ValueError('Integration update receipt changed or is missing')
    return op


def original_scope(basis, manifest, current):
    old = basis['manifest']
    for field in ('run_id', 'base_sha', 'feature_ref', 'target_ref'):
        if manifest[field] != old[field]:
            raise ValueError('Previous review belongs to a different branch run')
    if current['check_specifications'] != basis['candidate']['check_specifications']:
        raise ValueError('Required check scope changed')
    if current['workspace'] != basis['candidate']['workspace']:
        raise ValueError('The reviewed workspace changed')


def resolution_receipt(task, manifest, reuse, basis):
    """The already reviewed resolution must cover precisely the integrated tree."""
    op = update_for(task, reuse['update_id'])
    item_id = op.get('resolution_item')
    item = next((i for i in task['branch_run']['items'] if i['id'] == item_id), None)
    if not item:
        raise ValueError('Reviewed resolution item is missing')
    receipt = json.loads(item['commit_receipt']['receipt'])
    identity = receipt['id']
    rebuilt = json.loads(evidence.ready_receipt(receipt['candidate'], receipt['checks'], receipt['review'],
                         receipt['worker_model'], receipt['reviewer_model'], receipt['criteria_outcomes']))
    review_assessment.retained(receipt['review'], receipt['candidate']['id'])
    integration = receipt['review'].get('integration_review', {})
    old = basis['manifest']
    commits = manifest['commits']
    if (rebuilt != receipt or op.get('origin') != 'conflict_resolution'
            or commits[:-1] != old['commits'] or commits[-1]['item_id'] != item_id
            or commits[-1]['receipt_id'] != identity or commits[-1]['new_tip'] != op['old_tip']
            or commits[-1]['tree'] != manifest['feature_tree']
            or integration.get('task_tip') != old['feature_tip']
            or integration.get('target_tip') != op['target_tip']
            or integration.get('context_digest') != op.get('context_digest')
            or integration.get('candidate_tree') != manifest['feature_tree']
            or manifest['plan_revision'] != old['plan_revision'] + 1
            or requirements(manifest, item_id) != requirements(old)):
        raise ValueError('Resolution review does not cover this integration and original scope')
    rows = [r for r in manifest['requirements'] if r['item_id'] == item_id]
    if ([r['criterion'] for r in rows] != receipt['candidate']['criteria']
            or any(r['receipt_id'] != identity for r in rows)):
        raise ValueError('Resolution criteria or receipts changed')
    return receipt


def validate_basis(readiness, task, seen):
    from . import branch_final as final
    reuse = readiness['reuse']
    basis = basis_for(task, reuse['basis_id'])
    if not basis or basis['id'] in seen:
        raise ValueError('Previous approval is missing or cyclic')
    final.validate_record(basis, task, seen)
    old = basis['manifest']
    if (basis['candidate'].get('review_contract_version') != 1
            or readiness['candidate'].get('review_contract_version') != 1
            or not basis.get('review_input_digest')
            or readiness['review_input_digest'] != basis['review_input_digest']
            or final._hash({k: v for k, v in old.items() if k != 'id'}) != old['id']):
        raise ValueError('Prior review provenance or operator directions changed')
    original_scope(basis, readiness['manifest'], readiness['candidate'])
    return basis


def validate(readiness, task, seen=None):
    from . import branch_final as final
    seen = set(seen or ())
    if readiness['id'] in seen:
        raise ValueError('Cyclic integration approval')
    seen.add(readiness['id'])
    basis = validate_basis(readiness, task, seen)
    manifest = readiness['manifest']; old = basis['manifest']; reuse = readiness['reuse']
    if readiness['reviews']:
        raise ValueError('Integration receipts must not relabel earlier chunk approvals')
    if final._hash({k: v for k, v in manifest.items() if k != 'id'}) != manifest['id']:
        raise ValueError('Integration manifest changed')
    if reuse['mode'] == 'unchanged':
        omit = {'id', 'target_tip'}
        if ({k: v for k, v in manifest.items() if k not in omit} != {k: v for k, v in old.items() if k not in omit}
                or readiness['candidate'] != basis['candidate'] or readiness['checks'] != basis['checks']
                or any(readiness[k] != basis[k] for k in ('review', 'worker_model', 'reviewer_model'))):
            raise ValueError('Unchanged review inputs no longer match')
        return
    op = update_for(task, reuse['update_id'])
    if (op['new_tip'] != manifest['feature_tip'] or op['tree'] != manifest['feature_tree']
            or op['target_tip'] != manifest['review_base_sha']):
        raise ValueError('Update does not produce the reviewed candidate')
    if reuse['mode'] == 'resolved':
        receipt = resolution_receipt(task, manifest, reuse, basis)
        if any(readiness[k] != receipt[k] for k in ('review', 'worker_model', 'reviewer_model')):
            raise ValueError('Saved resolution approval changed')
        return
    if reuse['mode'] != 'integration':
        raise ValueError('Unknown integration review mode')
    if (op['old_tip'] != old['feature_tip'] or op.get('origin') == 'conflict_resolution'
            or manifest['commits'] != old['commits'] or requirements(manifest) != requirements(old)
            or any(manifest[k] != old[k] for k in ('plan_revision', 'plan_digest', 'plan_content_digest'))):
        raise ValueError('Integration changes exceed the previous approved scope')
    scope = scope_manifest(manifest, reuse)
    review = readiness['review']
    if (review.get('decision') != 'APPROVE' or review.get('manifest_id') != scope['id']
            or review.get('chunk_ids') != [c['id'] for c in scope['chunks']]
            or review.get('criteria_ids') != [r['id'] for r in manifest['requirements']]
            or review.get('reviewer_model') != readiness['reviewer_model']
            or evidence.model_identity(readiness['worker_model']) == evidence.model_identity(readiness['reviewer_model'])):
        raise ValueError('Focused integration review is incomplete or not independent')
    review_assessment.retained(review, final._hash({'manifest_id': scope['id'], 'chunk_ids': review['chunk_ids'],
                                                  'criteria_ids': review['criteria_ids'], 'page': None}))


def diff(task, basis, manifest):
    return work.source_git(task['branch_run']['workspace_mapping']['source'], 'diff', '--binary',
        '--no-ext-diff', '--no-textconv', '--no-renames', basis['manifest']['feature_tip'], manifest['feature_tip'], '--')


def same_candidate_manifest(left, right):
    # Live destination movement affects merge readiness, not the code inspected.
    omit = {'id', 'target_tip'}
    return {k: v for k, v in left.items() if k not in omit} == {k: v for k, v in right.items() if k not in omit}


def validate_diff(readiness, task):
    basis = basis_for(task, readiness['reuse']['basis_id'])
    if not basis or diff(task, basis, readiness['manifest']) != readiness['reuse']['diff']:
        raise ValueError('Integration diff no longer matches the two reviewed revisions')


def scope_manifest(manifest, reuse):
    from . import branch_final as final, review_context
    parts = review_context.chunks(reuse['diff'], final.CHUNK_SIZE)
    chunks = [{'id': f'integration:{i}', 'kind': 'diff', 'content': text,
               'digest': hashlib.sha256(text.encode()).hexdigest()} for i, text in enumerate(parts, 1)]
    scope = {**manifest, 'chunks': chunks, 'diff': reuse['diff'],
             'diff_bytes': len(reuse['diff'].encode()), 'diff_lines': len(reuse['diff'].splitlines()),
             'integration_basis': reuse['basis_id'],
             'target_tip': manifest['review_base_sha']}
    scope.pop('id')
    scope['id'] = final._hash(scope)
    return scope


def prepare(task, manifest, current, checks):
    """Conservative eligibility: missing/changed provenance uses ordinary review."""
    from . import branch_final as final
    history = task['branch_run'].get('previous_readiness', [])
    basis = history[-1] if history else None
    if not isinstance(basis, dict):
        return None
    trial = {'version': 2, 'manifest': manifest, 'candidate': current, 'checks': checks, 'reviews': [],
             'review_input_digest': input_digest(task), 'reuse': {'basis_id': basis.get('id'), 'mode': 'unchanged'},
             **{k: basis.get(k) for k in ('review', 'worker_model', 'reviewer_model')}}
    try:
        trial['id'] = final._hash(trial)
        validate(trial, task)
        return trial
    except (ValueError, KeyError, TypeError):
        pass
    updates = task['branch_run'].get('target_update_history', [])
    op = updates[-1] if updates else None
    if not op:
        return None
    try:
        trial['reuse'].update(mode='resolved' if op.get('origin') == 'conflict_resolution' else 'integration', update_id=op['digest'])
        if trial['reuse']['mode'] == 'resolved':
            # Removing only the controller-added resolution must recover the old plan.
            plan = copy.deepcopy(task['branch_run']['plan'])
            plan['items'] = [i for i in plan['items'] if i['id'] != op['resolution_item']]
            if final._hash(plan) != basis['manifest']['plan_content_digest']:
                return None
            receipt = resolution_receipt(task, manifest, trial['reuse'], basis)
            trial.update({k: receipt[k] for k in ('review', 'worker_model', 'reviewer_model')})
            trial.pop('id'); trial['id'] = final._hash(trial)
            validate(trial, task)
        else:
            validate_basis(trial, task, set())
            old = basis['manifest']
            update_for(task, op['digest'])
            if (op['old_tip'] != old['feature_tip'] or op['new_tip'] != manifest['feature_tip']
                    or op['tree'] != manifest['feature_tree'] or op['target_tip'] != manifest['review_base_sha']
                    or manifest['commits'] != old['commits'] or requirements(manifest) != requirements(old)
                    or any(manifest[k] != old[k] for k in ('plan_revision', 'plan_digest', 'plan_content_digest'))):
                return None
            trial['reuse']['diff'] = diff(task, basis, manifest)
        return trial
    except (ValueError, KeyError, TypeError):
        return None


def finalize(engine, runtime, manifest, current, checks):
    from . import branch_final as final, branch_disagreement, context_evidence
    task = runtime.task
    ready = prepare(task, manifest, current, checks)
    if ready is None:
        return None
    mode = ready['reuse']['mode']
    labels = {'unchanged': 'Reusing approval: review inputs and checks are unchanged.',
              'resolved': 'Reusing the independent conflict-resolution review. Final checks passed.',
              'integration': 'Keeping the earlier approval. Reviewing the update and its impact on the task.'}
    engine.event(task, 'review_reused', labels[mode], {'mode': mode, 'basis_id': ready['reuse']['basis_id']})
    final.recovery.guard(runtime)
    if mode == 'integration':
        scope = scope_manifest(manifest, ready['reuse'])
        basis = basis_for(task, ready['reuse']['basis_id'])
        reference = context_evidence.retain(task, {'previous_approval': basis, 'current_task_diff': manifest['diff']}, 'integration_review_basis')
        packet = {'manifest_id': scope['id'], 'diff': ready['reuse']['diff'], 'checks': checks,
                  'chunk_ids': [c['id'] for c in scope['chunks']], 'criteria_ids': [r['id'] for r in manifest['requirements']],
                  'requirements': requirements(manifest), 'location_index': manifest['files'],
                  'previous_approval_reference': reference,
                  'integration': {'from_tip': basis['manifest']['feature_tip'], 'to_tip': manifest['feature_tip'],
                                  'basis_id': basis['id']},
                  'instruction': 'Review the complete update delta and its interactions with the previously approved task. '
                  'The original approval remains bound to its earlier revision, not this combined candidate. '
                  'For each original criterion assess whether the update preserves it; inspect affected callers, dependencies, '
                  'configuration, styles and tests even when different files changed. Use current source and fresh checks. '
                  'The complete task diff and prior approval are available via read_context_evidence if broader inspection is needed. '
                  'Do not restart implementation or repeat unaffected review chunks. Report concrete regressions or approve the integration.'}
        from . import pr_description
        if pr_description.enabled(task):
            packet['publication_drafts'] = pr_description.item_drafts(manifest)
        overall = final.review_paged(engine, runtime, scope, packet,
                                    [c['id'] for c in scope['chunks']], [r['id'] for r in manifest['requirements']])
        ready.update(review=overall, worker_model=evidence.model_identity(task['providers']['worker']),
                     reviewer_model=overall.get('reviewer_model', final.recovery.model(task)))
    final.recovery.guard(runtime)
    now = final.build_manifest(task['branch_run'])
    if (not same_candidate_manifest(now, manifest)
            or evidence.candidate(task, current['context'], current['check_specifications'], current['criteria']) != current
            or input_digest(task) != ready['review_input_digest']):
        from .branch_pause import PauseError
        raise PauseError('branch_drift', stage='finalizing')
    if ready['review']['decision'] != 'APPROVE':
        return branch_disagreement.repair({**ready['review'], 'source_patch': manifest['diff']}, current['id'], checks)
    if mode == 'unchanged':
        basis = basis_for(task, ready['reuse']['basis_id'])
        if now == basis['manifest']:
            # Repeated rechecks keep the same receipt instead of growing a chain.
            return {'decision': 'APPROVE', 'readiness': copy.deepcopy(basis)}
    blocker = None
    try:
        work.source_git(task['branch_run']['workspace_mapping']['source'], 'merge-base', '--is-ancestor', now['target_tip'], manifest['feature_tip'])
    except ValueError:
        blocker = 'The target branch has new commits. Choose Update branch & recheck to combine them with the saved task before merging.'
    ready.update(manifest=now, integration_blocker=blocker)
    ready.pop('id', None); ready['id'] = final._hash(ready)
    final.validate_record(ready, task)
    return {'decision': 'APPROVE', 'readiness': ready}
