"""Independent synthetic contract; no exporter implementation or live state."""
import copy
import re
from cheapos import branch_runs

SHA = 'a1' * 20
BASE = 'b2' * 20
TASK_ID = '0123456789abcdef0123456789abcdef'
SECRET = 'OMIT_PRIVATE_SENTINEL'


def task():
    plan = {'items': [{'id': 'first', 'title': 'First item', 'instructions': SECRET,
                      'acceptance_criteria': ['Meets specification'], 'required_checks': ['python3 -V']}],
            'limits': {'requests': 10}, 'final_checks': ['python3 -V']}
    run = branch_runs.new_run(plan, original_request=SECRET, inputs={'document': SECRET},
                             base_ref='refs/heads/main', base_sha=BASE,
                             target_ref='refs/heads/main', feature_ref='refs/heads/feature/report',
                             now='2026-01-01T00:00:00Z', run_id='synthetic-run')
    run.update(status='ready_for_merge', expected_feature_tip=SHA,
               consumption={'working_seconds': 12.5, 'worker_tokens': 31, 'reviewer_tokens': 17},
               authorization_ref=SECRET, workspace_mapping={'run_id': run['id'],
               'feature_ref': run['feature_ref'], 'target_ref': run['target_ref'], 'source': '/'+SECRET})
    run['items'][0].update(status='committed', commit_receipt={
        'id': 'synthetic-operation', 'stage': 'completed', 'run_id': run['id'],
        'item_id': 'first', 'old_tip': BASE, 'new_tip': SHA, 'outcome': 'committed'})
    return {'id': TASK_ID, 'title': 'Synthetic report', 'status': 'approved', 'branch_run': run,
            'source': '/'+SECRET, 'workspace': '/'+SECRET, 'prompt': SECRET,
            'messages': [SECRET], 'events': [], 'patch': SECRET,
            'providers': {'worker': {'model': 'fixture/worker', 'api_key': SECRET, 'base_url': SECRET},
                          'reviewer': {'model': 'fixture/reviewer'}},
            'checks': [{'passed': True, 'output': SECRET}, {'passed': False, 'output': SECRET}],
            'checkpoints': [{'decision': 'APPROVE', 'feedback': SECRET}],
            'usage': {'worker': {'tokens': 31, 'cost': 0}, 'reviewer': {'tokens': 17, 'cost': 0},
                      'cost': 0, 'estimated_requests': 2, 'uncertain_requests': 0}}


def has(report, *values):
    assert isinstance(report, str) and report.strip(), 'Expected nonempty Markdown'
    for value in values:
        assert value.lower() in report.lower(), 'Missing report value: '+value


def private_absent(report):
    assert SECRET not in report, 'Private allowlist sentinel leaked'


def commit_present(report):
    has(report, SHA)


def commit_absent(report):
    assert SHA not in report, 'Unconfirmed commit SHA leaked as report evidence'


def unavailable(report):
    assert re.search(r'unavailable|unknown|not recorded', report, re.I), 'Missing accounting became zero'


def escaped(report):
    assert '|raw|' not in report and '\n# injected' not in report, 'Markdown label injection'
    has(report, '東京')
