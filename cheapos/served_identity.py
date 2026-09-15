"""Bounded provider-reported identity, distinct from requested route configuration."""
import re


def safe_model(value):
    if not isinstance(value,str) or not 1<=len(value)<=160 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/+-]*',value):return None
    if '://' in value or value.startswith(('sk-','Bearer')):return None
    return value


def opaque(value):
    value=(safe_model(value) or '').lower()
    return not value or any(part in {'auto','router','automatic','combo','combos'} for part in value.split('/'))


def metadata(requested, reported=None, conflict=False):
    served=safe_model(reported)
    if conflict or opaque(served):served=None
    return {'requested_model':safe_model(requested),'served_model':served,
            'identity_provenance':'response_model' if served else 'unknown',
            'gateway_internal_attempts':None,
            'independence_basis':'response_model' if served else 'unknown' if opaque(requested) else 'configured_named_routes'}


def apply(record, usage):
    """Provider metadata is internal; never trust extra usage/header keys directly."""
    saved=usage.pop('_served_identity',None) if isinstance(usage,dict) else None
    reported=saved.get('served_model') if isinstance(saved,dict) and saved.get('identity_provenance')=='response_model' else None
    record.update(metadata(record['model'],reported))


def normalized(value):
    value=(safe_model(value) or '').lower()
    if value.startswith('openrouter/'):value=value[len('openrouter/'):]
    return value[:-5] if value.endswith(':free') else value


def review_workers(task, record):
    """Exclude superseded inspection of a proven unchanged, committed item.

    Original authors remain in scope. Unknown identity is never excused for an
    item that changed the candidate, or when its provenance is incomplete.
    """
    workers=[q for q in task.get('request_metrics',[]) if q.get('role')=='worker' and q.get('dispatched')
             and q.get('purpose')!='probe']
    run=task.get('branch_run') or {}
    items=run.get('items',[])
    excluded=set()
    for item in items:
        original=next((i for i in items if i.get('id')==item.get('revision_of')),None)
        receipt=(original or {}).get('commit_receipt') or {}
        if not original or original.get('status')!='committed' or receipt.get('stage')!='completed' or not receipt.get('new_tip'):
            continue
        scope=(task.get('pending_review') or {}).get('identity_scope') or {}
        active=(record.get('review_candidate_id') and record['review_candidate_id']==scope.get('candidate_id')
                and scope.get('item_id')==item.get('id') and scope.get('no_change') is True
                and scope.get('feature_parent')==receipt['new_tip']==run.get('expected_feature_tip'))
        finished=(item.get('status')=='satisfied_without_change' and (item.get('evidence') or {}).get('no_change') is True
                  and (item.get('commit_receipt') or {}).get('stage')=='completed'
                  and (item.get('commit_receipt') or {}).get('new_tip')==receipt['new_tip'])
        if not (active or finished):continue
        attempts=[q for q in workers if q.get('branch_item_id')==item.get('id')]
        # Retain the current verification worker as well as all original authors.
        if attempts:
            excluded.update(q.get('id') for q in attempts[:-1] if q.get('id'))
    if excluded:
        record['identity_scope']={'basis':'unchanged_committed_revision','excluded_inspection_requests':sorted(excluded)}
    return [q for q in workers if q.get('id') not in excluded]


def ensure_independent(task, record):
    """Gate new review responses before tools/approval. No inference or retries.

    Exact named configurations retain existing policy when served metadata is
    absent: distinct-config comparison for Unattended/automatic work, while manual
    Interactive same-name configuration remains allowed. Neither proves underlying
    identity separation. Reported same served identities always block.
    Historical tasks without the version marker retain their existing policy.
    """
    if task.get('served_identity_version')!=1 or record.get('role')!='reviewer' or record.get('purpose')=='probe':return
    from .providers import ProviderError
    workers=review_workers(task,record)
    current=record.get('served_model') if record.get('identity_provenance')=='response_model' else None
    if opaque(record.get('requested_model')) and current is None:
        raise ProviderError('Reviewer route identity is unavailable; an opaque alias cannot establish independent review.',code='review_identity_unknown')
    for worker in workers:
        served=worker.get('served_model') if worker.get('identity_provenance')=='response_model' else None
        requested=worker.get('requested_model',worker.get('model'))
        if opaque(requested) and served is None:
            raise ProviderError('Worker route identity is unavailable; an opaque alias cannot establish independent review.',code='review_identity_unknown')
        actual_conflict=current is not None and served is not None and normalized(current)==normalized(served)
        strict=bool(task.get('branch_run')) or task.get('execution',{}).get('mode') in {'delegate','remote'}
        configured_conflict=strict and normalized(current or record.get('requested_model'))==normalized(served or requested)
        if actual_conflict or configured_conflict:
            raise ProviderError('Worker and reviewer resolve to the same reported or configured model. Independent review is required.',code='review_identity_conflict')
