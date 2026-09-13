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


def ensure_independent(task, record):
    """Gate new review responses before tools/approval. No inference or retries.

    Exact named configurations retain the existing distinct-config policy when
    served metadata is absent; that is explicitly not underlying identity proof.
    Historical tasks without the version marker retain their existing policy.
    """
    if task.get('served_identity_version')!=1 or record.get('role')!='reviewer' or record.get('purpose')=='probe':return
    from .providers import ProviderError
    workers=[q for q in task.get('request_metrics',[]) if q.get('role')=='worker' and q.get('dispatched')
             and q.get('purpose')!='probe']
    current=record.get('served_model') if record.get('identity_provenance')=='response_model' else None
    if opaque(record.get('requested_model')) and current is None:
        raise ProviderError('Reviewer route identity is unavailable; an opaque alias cannot establish independent review.',code='review_identity_unknown')
    for worker in workers:
        served=worker.get('served_model') if worker.get('identity_provenance')=='response_model' else None
        requested=worker.get('requested_model',worker.get('model'))
        if opaque(requested) and served is None:
            raise ProviderError('Worker route identity is unavailable; an opaque alias cannot establish independent review.',code='review_identity_unknown')
        if normalized(current or record.get('requested_model'))==normalized(served or requested):
            raise ProviderError('Worker and reviewer resolve to the same reported or configured model. Independent review is required.',code='review_identity_conflict')
