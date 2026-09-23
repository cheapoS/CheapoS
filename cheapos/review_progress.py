"""Incremental reviewer assessments; evidence validation is never final approval."""
import copy

from . import review_assessment as evidence
from .instructions.runtime import prompt


def targets(state):
    return {**{f'criterion:{i + 1}': key for i, key in enumerate(state['criteria'])},
            'regressions': 'Regression assessment', 'verification': 'Verification assessment',
            'limitations': 'Verification limitations'}


def bind(state, directions):
    basis = evidence.digest({'scope': state['scope'], 'criteria': state['criteria'],
                             'directions': directions, 'criterion_checks': state.get('criterion_checks', {})})
    if state.get('progress', {}).get('basis') != basis:
        state['progress'] = {'basis': basis, 'assessments': {}}


def validate(state, target, value):
    labels = targets(state)
    if target not in labels:
        raise ValueError('Unknown review target. Use an exact current review_progress target ID.')
    if target == 'limitations':
        if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
            raise ValueError('Limitations must be an array of concrete limitations; use [] when none remain.')
        return
    sources = state.get('criterion_checks', {}).get(labels[target]) if target.startswith('criterion:') else None
    issues = []
    evidence.assess_claim(state, value, labels[target], target, issues=issues, excerpts={},
                          implementation=target == 'regressions' or target.startswith('criterion:') and sources is None,
                          verification=target == 'verification', required_sources=sources)
    if issues:
        raise evidence.EvidenceError(issues, state)


def current(state):
    result = {}
    for target, value in state.get('progress', {}).get('assessments', {}).items():
        try:
            validate(state, target, value)
        except (ValueError, TypeError):
            continue  # Changed/missing sources cannot carry a claim forward.
        result[target] = copy.deepcopy(value)
    return result


def display(state):
    recorded = current(state)
    questions = targets(state)
    remaining = [key for key in questions if key not in recorded]
    return {'scope': state['scope'], 'targets': questions, 'recorded_assessments': recorded,
            'remaining': remaining, 'next_target': remaining[0] if remaining else None,
            'ready_for_final_decision': not remaining, 'approved': False}


def record(state, candidate_id, target, reason=None, citations=None, limitations=None):
    if candidate_id != state['scope']:
        raise ValueError('Progress belongs to a stale candidate. No assessment was recorded.')
    value = limitations if target == 'limitations' else {'reason': reason, 'citations': citations}
    validate(state, target, value)
    advanced = target not in current(state)
    state['progress']['assessments'][target] = copy.deepcopy(value)
    return {'recorded': target, 'advanced': advanced, 'review_progress': display(state)}


def tools(tools, state, decision_name='review_decision'):
    tools = copy.deepcopy(tools)
    decision = next(t for t in tools if t['function']['name'] == decision_name)['function']['parameters']
    decision['properties']['use_recorded_assessment'] = {
        'type': 'boolean', 'description': 'On APPROVE, true explicitly confirms every recorded assessment, including inherited assessments. The controller revalidates all claims; incomplete progress cannot approve. Otherwise supply the full review_assessment.'}
    decision['properties']['review_assessment']['description'] = (
        'On APPROVE, supply this complete assessment unless use_recorded_assessment is true. '
        'Use exactly one form; neither partial progress nor recording every target approves by itself.')
    claim = evidence.schema(state)['properties']['regressions']['properties']
    tools.append({'type': 'function', 'function': {
        'name': 'record_review_progress',
        'description': 'Record one evidence-backed assessment for this candidate. Use target IDs from review_progress. This saves review work but never approves, edits files, runs commands or changes scope. For limitations, supply limitations instead of reason/citations.',
        'parameters': {'type': 'object', 'properties': {
            'candidate_id': {'type': 'string', 'enum': [state['scope']]},
            'target': {'type': 'string', 'enum': list(targets(state))},
            'reason': claim['reason'], 'citations': claim['citations'],
            'limitations': {'type': 'array', 'items': {'type': 'string'}}},
            'required': ['candidate_id', 'target'], 'additionalProperties': False}}})
    return tools


def instruction():
    return prompt('review_progress')


def complete(state, result):
    if result.get('use_recorded_assessment') is not True:
        return  # Existing full decisions still use the unchanged evidence gate.
    # Never fill a partly supplied, contradictory final assessment implicitly.
    if 'review_assessment' in result:
        raise ValueError('Either confirm recorded assessments or supply a full review_assessment, not both. '
                         'To submit a full review_assessment, omit use_recorded_assessment or set it to false. '
                         'Set it to true only to confirm already recorded assessments, without review_assessment.')
    recorded = current(state)
    if any(key not in recorded for key in targets(state)):
        raise ValueError('Recorded review is incomplete. Resolve the remaining review_progress targets before approval.')
    result['review_assessment'] = {
        'criteria': {key: recorded[f'criterion:{i + 1}'] for i, key in enumerate(state['criteria'])},
        **{key: recorded[key] for key in ('regressions', 'verification', 'limitations')}}
    # The ordinary final gate validates this again and creates the receipt only
    # after candidate/check revalidation and an explicit independent decision.
