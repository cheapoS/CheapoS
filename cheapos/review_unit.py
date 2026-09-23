"""Small model-facing protocol for a controller-bound review unit.

Short handles refer only to delivered excerpts; identity/coverage are injected
from the active controller unit, never guessed from a model's prose.
"""
import copy
from . import review_assessment as evidence, review_progress as progress


def handles(state):
    saved = state.setdefault('unit_evidence_handles', {})
    for excerpt_id, row in state.get('excerpts', {}).items():
        ref = {'source': row['source'], 'excerpt_id': excerpt_id}
        if ref not in saved.values():
            saved['e' + str(len(saved) + 1)] = ref
    return {key: value for key, value in saved.items() if evidence.cited_excerpt(state, value) is not None}


def delivered(state, result):
    if not isinstance(result, dict):
        return result
    ref = result.get('citation')
    if ref:
        handle = next((key for key, value in handles(state).items() if value == ref), None)
        if handle:
            return {**result, 'evidence_handle': handle}
    return result


def initial_evidence(state):
    """Deliver actual small excerpts, never infer that a check proves behavior."""
    result, size = [], 0
    required = [source for sources in state.get('criterion_checks', {}).values() for source in sources]
    candidates = list(dict.fromkeys(required + list(state['sources'])))
    for source in candidates:
        if size >= 12000:
            break
        record = state['sources'][source]
        content = record['content'][:min(4000, 12000 - size)]
        value = delivered(state, {'evidence_id': source, 'kind': record['kind'],
            'content': content, 'offset': 0, 'next_offset': len(content),
            'has_more': len(content) < len(record['content']),
            'citation': evidence.citation(state, source, 0, len(content))})
        result.append(value); size += len(content)
    return result


def tools(offered, state):
    result = copy.deepcopy(offered)
    decision = next(t for t in result if t['function']['name'] == 'final_review_decision')['function']['parameters']
    for key in ('manifest_id', 'chunk_ids', 'criteria_ids', 'review_assessment'):
        decision['properties'].pop(key, None)
        if key in decision['required']:
            decision['required'].remove(key)
    claim = {'type': 'object', 'properties': {
        'target': {'type': 'string', 'description': 'Exact target from review_progress, e.g. criterion:1 or regressions.'},
        'reason': {'type': 'string', 'description': 'Concise judgment grounded in the evidence, not a quotation.'},
        'evidence': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Delivered evidence_handle values such as e1.'},
        'limitations': {'type': 'array', 'items': {'type': 'string'}}},
        'required': ['target'], 'additionalProperties': False}
    defect = decision['properties'].get('defects', {}).get('items', {}).get('properties', {}).get('criterion', {})
    defect.pop('enum', None)
    defect['description'] = 'Exact original requirement ID implicated by the defect; see the supplied requirements or complete_task_reference.'
    decision['properties']['assessments'] = {'type': 'array', 'items': claim,
        'description': 'Assess the assigned targets and explicitly approve this unit. Omit when confirming already recorded assessments.'}
    decision['properties']['use_recorded_assessment'] = {'type': 'boolean',
        'description': 'True explicitly confirms the complete saved assessment of this unit. Do not combine with assessments.'}
    record = next(t for t in result if t['function']['name'] == 'record_review_progress')
    record['function']['parameters'] = copy.deepcopy(claim)
    record['function']['description'] = 'Save one provisional assessment; it never approves. Use final_review_decision separately to approve or request changes.'
    return result


def expand(state, record):
    record = copy.deepcopy(record)
    if 'evidence' in record:
        if 'citations' in record:
            raise ValueError('Supply evidence handles or legacy citations, not both.')
        refs = handles(state)
        keys = record.pop('evidence')
        if not isinstance(keys, list) or any(not isinstance(key, str) or key not in refs for key in keys):
            raise ValueError('Unknown or stale evidence handle. Use a delivered handle from this unit.')
        record['citations'] = [copy.deepcopy(refs[key]) for key in keys]
    record.setdefault('candidate_id', state['scope'])
    return record


def decision(state, result, expected, unit_id):
    result = copy.deepcopy(result)
    for key, value in {**expected, 'unit_id': unit_id}.items():
        if key in result and result[key] != value:
            raise ValueError('Review decision contains stale coverage: ' + key)
        result[key] = copy.deepcopy(value)
    if 'assessments' in result:
        if result.get('decision') != 'APPROVE' or result.get('use_recorded_assessment') or 'review_assessment' in result:
            raise ValueError('Use assessments only with an explicit APPROVE, without another assessment form.')
        records = result.pop('assessments')
        if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
            raise ValueError('assessments must be a list of target judgments.')
        targets = [row.get('target') for row in records]
        if any(not isinstance(target, str) for target in targets) or len(set(targets)) != len(targets):
            raise ValueError('Each assessment needs a distinct target.')
        staged = copy.deepcopy(state)
        for row in records:
            progress.record(staged, **expand(staged, row))
        result['use_recorded_assessment'] = True
        progress.complete(staged, result)
        result.pop('use_recorded_assessment')
        # The normal validator creates the receipt; a malformed decision never
        # partially saves assertions or creates an approval.
    return result
