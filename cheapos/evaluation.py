"""Read-only, local trial comparisons. A manifest is evidence metadata, not authority."""
import hashlib
import itertools
import json
import re
from pathlib import Path

from . import metrics

CONTRACT_FIELDS = ('source_sha256', 'requirements_sha256', 'checks_sha256',
                   'environment_sha256', 'authority_sha256')
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z')
SHA = re.compile(r'[a-f0-9]{64}\Z')
OBSERVATION_FIELDS = ('guidance', 'followups', 'read_calls', 'repeated_reads', 'repair_attempts',
                      'check_repair_cycles', 'review_repair_cycles',
                      'open_check_repair_cycles', 'open_review_repair_cycles')
COVERAGE = {'complete_instrumented', 'partial_historical'}
COST_PROVENANCE = {'provider_reported', 'estimated', 'uncertain_reservation',
                   'scripted_no_model_requests', 'includes_uncertain_reservations',
                   'mixed_reported_and_estimated', 'includes_estimates', 'unknown'}

LIMITATIONS = (
    'Local observational evidence, not a billing receipt or causal model ranking. '
    'Contract fingerprints and completion assessments are operator supplied. '
    'Matching fingerprints do not independently verify experimental control. '
    'Scripted fixtures validate the controller, not model quality. '
    'Unknowns are null; retained event counts are lower bounds. '
    'Active elapsed time excludes gaps between runs. No inference or telemetry is performed.'
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('Trial, case and variant IDs must be 1–80 safe identifier characters')
    return value


def _fingerprint(value):
    if value is not None and (not isinstance(value, str) or not SHA.fullmatch(value)):
        raise ValueError('Evidence fingerprints must be lowercase SHA-256 or null')
    return value


def _sum_known(values):
    return metrics.number(sum(values)) if all(metrics.number(v) is not None for v in values) else None


def observations(task):
    """Count retained events without promoting incomplete history to complete totals."""
    events = task.get('events')
    if not isinstance(events, list):
        return {'coverage': 'unavailable', **dict.fromkeys(OBSERVATION_FIELDS)}
    seen_events, seen_reads = set(), set()
    result = {'coverage': 'retained_events_lower_bound', **dict.fromkeys(OBSERVATION_FIELDS, 0)}
    check_repairs, review_repairs = set(), set()
    followup = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        identity = event.get('id')
        if identity and identity in seen_events:
            continue
        if identity:
            seen_events.add(identity)
        kind = event.get('kind')
        if kind == 'steer': result['guidance'] += 1
        if kind == 'user':
            result['followups'] += 1
            followup += 1
        if kind == 'repair_attempt': result['repair_attempts'] += 1
        detail = event.get('detail')
        detail = detail if isinstance(detail, dict) else {}
        scope = (event.get('branch_run_id'), detail.get('item_id', event.get('item_id')), followup)
        if kind == 'checks' and isinstance(detail.get('command'), list) and detail['command']:
            key = digest([scope, detail['command'], detail.get('directory', '.')])
            if detail.get('passed') is False: check_repairs.add(key)
            elif detail.get('passed') is True and key in check_repairs:
                result['check_repair_cycles'] += 1
                check_repairs.remove(key)
        if kind == 'repair_attempt' or kind == 'review' and detail.get('decision') == 'REQUEST_CHANGES':
            review_repairs.add(scope)
        elif kind == 'review' and detail.get('decision') == 'APPROVE' and scope in review_repairs:
            result['review_repair_cycles'] += 1
            review_repairs.remove(scope)
        if kind != 'tool' or event.get('title') not in ('read file', 'read url'):
            continue
        args, output = detail.get('arguments') or {}, detail.get('result') or {}
        if not isinstance(args, dict) or not isinstance(output, dict) or not isinstance(output.get('content'), str):
            continue
        source = output.get('source_url', args.get('url')) if event['title'] == 'read url' else args.get('path')
        if not isinstance(source, str): continue
        # Volatile fetch times and receipt IDs are deliberately not read identity.
        key = digest([event.get('branch_run_id'), event.get('item_id'),
                      event['title'], source, output['content']])
        result['read_calls'] += 1
        result['repeated_reads'] += key in seen_reads
        seen_reads.add(key)
    result['open_check_repair_cycles'] = len(check_repairs)
    result['open_review_repair_cycles'] = len(review_repairs)
    return result


def _measurements(summary, observed):
    roles = summary.get('roles') or {}
    values = {}
    for role in ('worker', 'reviewer', 'planner', 'coordinator'):
        for field in ('tokens', 'cost'):
            values[role + '_' + field] = metrics.number((roles.get(role) or {}).get(field))
    for field in ('tokens', 'cost'):
        values['worker_reviewer_' + field] = _sum_known([values[r + '_' + field] for r in ('worker', 'reviewer')])
    values['total_accounted_cost'] = metrics.number((summary.get('cost') or {}).get('accounted'))
    values['total_accounted_tokens'] = _sum_known([values[r + '_tokens'] for r in ('worker', 'reviewer', 'planner', 'coordinator')])
    for key in ('elapsed_seconds', 'provider_request_seconds', 'provider_cooldown_seconds',
                'operator_wait_seconds', 'controller_work_seconds'):
        values[key] = metrics.number((summary.get('time') or {}).get(key))
    operator = summary.get('operator') or {}
    values['check_approval_requests'] = metrics.number(operator.get('check_approvals_requested'))
    values['resumes'] = metrics.number(operator.get('resumes'))
    for key in OBSERVATION_FIELDS:
        values[key] = observed.get(key)
    decisions = (summary.get('reviews') or {}).get('decisions')
    values['review_revision_decisions'] = decisions.count('REQUEST_CHANGES') if isinstance(decisions, list) else None
    checks = summary.get('checks') or {}
    values['failed_check_runs'] = (checks['runs'] - checks['passed']
                                   if all(metrics.number(checks.get(k)) is not None for k in ('runs', 'passed')) else None)
    return values


def request_provenance(task):
    result = {}
    for role in ('worker', 'reviewer', 'planner', 'coordinator'):
        records, seen = [], set()
        for index, record in enumerate(task.get('request_metrics', [])):
            identity = record.get('id') or ('row', index)
            if record.get('role') == role and record.get('dispatched') and identity not in seen:
                records.append(record)
                seen.add(identity)
        available = 'request_metrics' in task
        result[role] = {
            'coverage': 'retained_requests' if 'request_metrics' in task else 'unavailable',
            'dispatched': len(records) if available else None,
            'probes': sum(r.get('purpose') == 'probe' for r in records) if available else None,
            'failed': sum(r.get('status') == 'failed' for r in records) if available else None,
            'unreconciled': sum(r.get('usage_reconciled') is not True for r in records) if available else None,
            'cost_provenance': sorted({r.get('cost_provenance') if r.get('cost_provenance') in COST_PROVENANCE else 'unknown' for r in records}),
            'reported_tokens': _sum_known([metrics.number(r.get(k)) for r in records for k in ('input_tokens', 'output_tokens')]) if records else None,
        }
    return result


def load_trials(manifest, base):
    if not isinstance(manifest, dict) or type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1:
        raise ValueError('Unsupported trial manifest schema')
    entries = manifest.get('trials')
    if not isinstance(entries, list) or not entries:
        raise ValueError('A trial manifest needs a nonempty trials list')
    trials, identities, slots = [], set(), set()
    for entry in entries:
        trial_id, case, variant = (_identifier(entry.get(k)) for k in ('id', 'case', 'variant'))
        repeat = entry.get('repeat')
        if type(repeat) is not int or repeat < 1: raise ValueError('repeat must be a positive integer')
        slot = (case, variant, repeat)
        if trial_id in identities or slot in slots: raise ValueError('Duplicate trial ID or case/variant/repeat')
        identities.add(trial_id); slots.add(slot)
        contract = entry.get('contract') or {}
        contract = {key: _fingerprint(contract.get(key)) for key in CONTRACT_FIELDS}
        kind = entry.get('kind')
        if kind not in ('recorded_model_trial', 'scripted_controller'):
            raise ValueError('Explicit recorded_model_trial or scripted_controller kind required')
        source = entry.get('source')
        if not isinstance(source, str) or not source: raise ValueError('A local source JSON file is required')
        raw = (Path(base) / source).read_bytes()
        document = json.loads(raw)
        source_digest = hashlib.sha256(raw).hexdigest()
        completed, completion_source, assessment_digest = None, 'unavailable', None
        measurement = None
        source_identity = None
        request_evidence = None
        if kind == 'scripted_controller':
            if document.get('mode') != 'deterministic_scripted_providers' or type(document.get('schema_version')) is not int or document['schema_version'] != 1:
                raise ValueError('Scripted trials require an existing deterministic benchmark export')
            matches = [f for f in document.get('fixtures', []) if f.get('fixture_id') == entry.get('fixture_id')]
            if len(matches) != 1: raise ValueError('Benchmark fixture must match exactly once')
            summary = matches[0]
            source_identity = digest([source_digest, entry.get('fixture_id')])
            baseline = _fingerprint(summary.get('baseline_sha256'))
            if not baseline: raise ValueError('Benchmark fixture baseline is missing')
            # Existing fixtures fingerprint source and requirement together.
            contract['source_sha256'] = baseline
            contract['requirements_sha256'] = baseline
            completed = summary.get('verified_outcome') if type(summary.get('verified_outcome')) is bool else None
            completion_source = 'scripted_fixture_assertions'
            observed = observations({})
        else:
            if not isinstance(document, dict) or not isinstance(document.get('id'), str) or document.get('demo') or 'fixtures' in document:
                raise ValueError('Recorded trials require a saved non-demo task snapshot')
            summary = metrics.aggregate(document)
            source_identity = digest(['task', document['id']])
            request_evidence = request_provenance(document)
            observed = observations(document)
            plan = (document.get('branch_run') or {}).get('plan') or {}
            measurement = plan.get('measurement')
            if type(measurement) is not bool: measurement = None
            assessment = entry.get('assessment')
            if assessment is not None:
                if type(assessment.get('completed')) is not bool or not assessment.get('evidence_sha256'):
                    raise ValueError('Completion assessment requires a boolean and evidence fingerprint')
                assessment_digest = _fingerprint(assessment['evidence_sha256'])
                completed, completion_source = assessment['completed'], 'operator_assessment'
        if any(t['source_identity'] == source_identity for t in trials):
            raise ValueError('A task or fixture snapshot may appear only once per manifest')
        values = _measurements(summary, observed)
        if kind == 'recorded_model_trial':
            if 'checks' not in document: values['failed_check_runs'] = None
            if 'checkpoints' not in document: values['review_revision_decisions'] = None
            if 'events' not in document:
                values['check_approval_requests'] = values['resumes'] = None
        trials.append({'id': trial_id, 'case': case, 'variant': variant, 'repeat': repeat,
                       'kind': kind, 'contract': contract, 'snapshot_sha256': source_digest,
                       'measurement': measurement, 'source_identity': source_identity,
                       'request_evidence': request_evidence, 'completion': {'completed': completed,
                       'provenance': completion_source, 'evidence_sha256': assessment_digest},
                       'coverage': summary.get('coverage') if summary.get('coverage') in COVERAGE else 'unavailable',
                       'cost_provenance': ((summary.get('cost') or {}).get('provenance')
                           if (summary.get('cost') or {}).get('provenance') in COST_PROVENANCE else 'unknown'),
                       'observation_coverage': observed['coverage'], 'measurements': values})
    return trials


def compare(trials):
    pairs = []
    for left, right in itertools.combinations(trials, 2):
        if (left['case'], left['repeat']) != (right['case'], right['repeat']) or left['variant'] == right['variant']:
            continue
        reasons = []
        if left['kind'] != right['kind']: reasons.append('Different evidence kinds')
        if left['source_identity'] == right['source_identity']: reasons.append('Same task or fixture snapshot is not an independent trial')
        if left['measurement'] != right['measurement']: reasons.append('Different measurement modes')
        if left['kind'] == 'recorded_model_trial' and left['measurement'] is None:
            reasons.append('Measurement mode is unknown')
        for key in CONTRACT_FIELDS:
            if not left['contract'][key] or not right['contract'][key]: reasons.append('Missing ' + key)
            elif left['contract'][key] != right['contract'][key]: reasons.append('Different ' + key)
        comparable = not reasons
        matched_success = comparable and all(t['completion']['completed'] is True for t in (left, right))
        deltas = {}
        for key, value in left['measurements'].items():
            other = right['measurements'][key]
            # Behavioral observations are lower bounds, never exact efficiency deltas.
            exact = key not in {*OBSERVATION_FIELDS, 'review_revision_decisions', 'failed_check_runs'}
            deltas[key] = other - value if matched_success and exact and value is not None and other is not None else None
        pairs.append({'left': left['id'], 'right': right['id'], 'comparable': comparable,
                      'reasons': reasons, 'matched_success': matched_success,
                      'delta_right_minus_left': deltas})
    counts = []
    for kind, variant in sorted({(t['kind'], t['variant']) for t in trials}):
        selected = [t for t in trials if (t['kind'], t['variant']) == (kind, variant)]
        counts.append({'kind': kind, 'variant': variant, 'trials': len(selected),
                       'completed': sum(t['completion']['completed'] is True for t in selected),
                       'incomplete': sum(t['completion']['completed'] is False for t in selected),
                       'unknown': sum(t['completion']['completed'] is None for t in selected)})
    return {'schema_version': 1, 'scope': 'local_trial_comparison', 'trials': trials,
            'completion_counts': counts,
            'pairs': pairs, 'unpaired_trials': [t['id'] for t in trials if not any(t['id'] in (p['left'], p['right']) for p in pairs)],
            'limitations': LIMITATIONS}


def report(manifest, base):
    return compare(load_trials(manifest, base))


def markdown(result):
    lines = ['# Local trial comparison', '', result['limitations'], '',
             'Completion is an explicit operator assessment or scripted fixture assertion; a task status alone is not proof.', '']
    lines += ['| Evidence kind | Variant | Trials | Completed | Incomplete | Unknown |',
              '| --- | --- | ---: | ---: | ---: | ---: |']
    lines += [f"| {c['kind']} | {c['variant']} | {c['trials']} | {c['completed']} | {c['incomplete']} | {c['unknown']} |" for c in result['completion_counts']]
    lines += ['']
    for trial in result['trials']:
        lines += ['## ' + trial['id'], '',
                  f"Case: {trial['case']}; variant: {trial['variant']}; repeat: {trial['repeat']}; kind: {trial['kind']}",
                  f"Completion: {'unavailable' if trial['completion']['completed'] is None else trial['completion']['completed']}; provenance: {trial['completion']['provenance']}",
                  f"Usage coverage: {trial['coverage']}; cost: {trial['cost_provenance']}; observations: {trial['observation_coverage']}", '',
                  '| Measurement | Value |', '| --- | ---: |']
        lines += [f"| {key} | {'unavailable' if value is None else value} |" for key, value in trial['measurements'].items()]
        lines += ['']
    for pair in result['pairs']:
        lines += [f"## {pair['left']} → {pair['right']}", '',
                  'Comparable: ' + str(pair['comparable']) + '; matched completion: ' + str(pair['matched_success']),
                  '; '.join(pair['reasons']) or 'Declared comparison contracts match.', '',
                  '| Measurement | Delta (right − left) |', '| --- | ---: |']
        lines += [f"| {key} | {'unavailable' if value is None else value} |" for key, value in pair['delta_right_minus_left'].items()]
        lines += ['']
    if result['unpaired_trials']: lines += ['Unpaired trials: ' + ', '.join(result['unpaired_trials']), '']
    return '\n'.join(lines)
