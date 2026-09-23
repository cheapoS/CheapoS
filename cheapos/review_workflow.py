"""Durable final review units and deterministic composition of explicit decisions.

The model judges a bounded unit; the controller owns coverage and scheduling.
A unit receipt never authorizes execution, a merge, or a new spending policy.
"""
import copy
import time

from . import review_assessment as evidence
from . import branch_final_recovery as recovery

VERSION = 1
# Payload partition sizes, not request/iteration/work limits. Nothing is omitted.
MAX_CRITERIA = 4
MAX_REQUIREMENT_CHARS = 4000


def units(requirements):
    if len(requirements) <= MAX_CRITERIA and sum(len(row['criterion']) for row in requirements) <= MAX_REQUIREMENT_CHARS:
        return [_unit('complete', requirements)]
    result, group, size = [], [], 0
    for row in requirements:
        width = len(row['criterion'])
        if group and (len(group) >= MAX_CRITERIA or size + width > MAX_REQUIREMENT_CHARS
                      or row['item_id'] != group[0]['item_id']):
            result.append(_unit('requirements', group)); group, size = [], 0
        group.append(row); size += width
    if group:
        result.append(_unit('requirements', group))
    result.append(_unit('integration', []))
    return result


def _unit(kind, requirements):
    rows = [{key: row[key] for key in ('id', 'item_id', 'criterion')} for row in requirements]
    return {'version': VERSION, 'id': kind + ':' + evidence.digest(rows)[:20],
            'kind': kind, 'requirements': rows, 'criteria_ids': [row['id'] for row in rows]}


def scope(manifest_id, chunks, criteria, unit_id):
    from .branch_final import _hash
    return _hash({'manifest_id': manifest_id, 'chunk_ids': chunks, 'criteria_ids': criteria,
                  'page': None, 'unit_id': unit_id})


def begin(task, manifest, packet):
    from .branch_review_reuse import input_digest
    definitions = units(packet['requirements'])
    basis = evidence.digest({'manifest': manifest['id'], 'inputs': input_digest(task),
                             'checks': packet['checks'], 'units': definitions, 'version': VERSION})
    workflows = task['branch_run'].setdefault('review_workflows', {})
    state = workflows.setdefault(basis, {'version': VERSION, 'manifest_id': manifest['id'],
        'basis': basis, 'units': definitions, 'results': {}, 'status': 'pending', 'active_unit': None})
    if state.get('units') != definitions or state.get('basis') != basis:
        raise ValueError('Saved review workflow definition changed')
    task['branch_run']['active_review_workflow'] = basis
    return state


def validate_unit(result, unit, manifest_id, chunks, task):
    from .branch_final import _independent
    from .branch_disagreement import decision
    expected = {'manifest_id': manifest_id, 'chunk_ids': chunks,
                'criteria_ids': unit['criteria_ids'], 'unit_id': unit['id']}
    if not isinstance(result, dict) or any(result.get(k) != v for k, v in expected.items()):
        raise ValueError('Review unit coverage is stale or incomplete')
    if decision(result) != 'APPROVE' or not result.get('reviewer_model'):
        raise ValueError('Review unit requires an explicit independent approval')
    _independent(task, result['reviewer_model'])
    evidence.retained(result, scope(manifest_id, chunks, unit['criteria_ids'], unit['id']))
    assessment = result['review_assessment']
    expected_fields = ({'criteria'} if unit['kind'] == 'requirements' else
                       {'regressions', 'verification', 'limitations'} if unit['kind'] == 'integration' else
                       {'criteria', 'regressions', 'verification', 'limitations'})
    if set(assessment) != expected_fields:
        raise ValueError('Review unit assessment does not match its assigned coverage')
    if unit['kind'] != 'integration' and set(assessment['criteria']) != set(unit['criteria_ids']):
        raise ValueError('Review unit requirement coverage is incomplete')


def compose(manifest, definitions, decisions, task):
    from .branch_final import _hash
    chunks = [c['id'] for c in manifest['chunks']]
    if len(decisions) != len(definitions):
        raise ValueError('Review workflow is incomplete')
    if not definitions or definitions[-1]['kind'] not in ('integration', 'complete'):
        raise ValueError('Review workflow requires an integration decision')
    for unit, result in zip(definitions, decisions):
        validate_unit(result, unit, manifest['id'], chunks, task)
    integration = decisions[-1]
    criteria = {key: value for result in decisions for key, value in result['review_assessment'].get('criteria', {}).items()}
    expected = [r['id'] for r in manifest['requirements']]
    if set(criteria) != set(expected):
        raise ValueError('Review workflow requirement coverage is incomplete')
    assessment = {'criteria': criteria, **copy.deepcopy(integration['review_assessment'])}
    combined = {'decision': 'APPROVE', 'manifest_id': manifest['id'], 'chunk_ids': chunks,
        'criteria_ids': expected, 'feedback': integration['feedback'],
        'reviewer_model': integration['reviewer_model'], 'review_assessment': assessment,
        'workflow': {'version': VERSION, 'units': copy.deepcopy(decisions)}}
    for key in ('pull_request', 'suggestions', 'context_references'):
        if key in integration:
            combined[key] = copy.deepcopy(integration[key])
    excerpts = {unit['id'] + ':' + source: value for unit, result in zip(definitions, decisions)
                for source, value in result['_review_evidence'].get('excerpts', {}).items()}
    combined['_review_evidence'] = {'version': evidence.VERSION,
        'scope': _hash({'manifest_id': manifest['id'], 'chunk_ids': chunks, 'criteria_ids': expected, 'page': None}),
        'assessment_digest': evidence.digest(assessment), 'excerpts': excerpts,
        'composition_digest': evidence.digest(decisions)}
    return combined


def validate(overall, manifest, task):
    workflow = overall.get('workflow')
    if not isinstance(workflow, dict) or workflow.get('version') != VERSION:
        raise ValueError('Unsupported review workflow receipt')
    rebuilt = compose(manifest, units(manifest['requirements']), workflow.get('units', []), task)
    if overall != rebuilt:
        raise ValueError('Review evidence workflow receipt changed')


def run(engine, runtime, manifest, packet, review):
    """Persist boundaries and skip only validated, identical-candidate decisions."""
    from .context_evidence import retain
    task = runtime.task
    state = begin(task, manifest, packet)
    chunks = [c['id'] for c in manifest['chunks']]
    whole = retain(task, packet, 'review_workflow_evidence')
    decisions = []
    for index, unit in enumerate(state['units']):
        recovery.guard(runtime)
        saved = state['results'].get(unit['id'])
        if saved is not None:
            validate_unit(saved, unit, manifest['id'], chunks, task)
            decisions.append(copy.deepcopy(saved))
            continue
        state.update(status='reviewing', active_unit=unit['id'])
        engine.store.save(task)  # Persist dispatch intent before a provider request.
        engine.event(task, 'review_progress', 'Reviewing requirements' if unit['kind'] == 'requirements' else 'Reviewing integration',
            {'manifest_id': manifest['id'], 'unit_index': index + 1, 'unit_total': len(state['units']),
             'criteria_ids': unit['criteria_ids'], 'approved_units': len(decisions), 'approved': False})
        current = copy.deepcopy(packet)
        current.update(review_unit=unit, criteria_ids=unit['criteria_ids'], requirements=unit['requirements'],
                       complete_task_reference=whole)
        current.pop('instruction', None)
        if unit['kind'] in ('integration', 'complete'):
            current['requirements'] = packet['requirements']
            current['completed_requirement_reviews'] = retain(task, decisions, 'review_workflow_decisions')
            current['coverage_summary'] = [{'criteria_ids': d['criteria_ids'], 'decision': d['decision'],
                                           'feedback': d['feedback']} for d in decisions]
        else:
            current.pop('publication_drafts', None)
        start = time.time()
        result = review(engine, runtime, manifest, current, chunks, unit['criteria_ids'],
                        progress={'unit_index': index + 1, 'unit_total': len(state['units'])})
        recovery.guard(runtime)
        state.setdefault('activity', {})[unit['id']] = {'last_decision_seconds': round(time.time() - start, 3),
                                                      'decision': result['decision']}
        if result['decision'] != 'APPROVE':
            state.update(status='changes_requested', last_rejection=copy.deepcopy(result))
            engine.store.save(task)
            return result
        validate_unit(result, unit, manifest['id'], chunks, task)
        state['results'][unit['id']] = copy.deepcopy(result)
        decisions.append(result)
        engine.store.save(task)  # An interruption of the next unit cannot replay this one.
    result = compose(manifest, state['units'], decisions, task)
    state.update(status='complete', active_unit=None)
    engine.store.save(task)
    engine.event(task, 'review', 'Independent review completed', {
        'manifest_id': manifest['id'], 'decision': 'APPROVE', 'approved_units': len(decisions),
        'feedback': result['feedback']})
    return result
