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
        'item_id': 'first', 'old_tip': BASE, 'new_tip': SHA, 'outcome': 'ready'})
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
    assert not re.search(r'(?<![a-fA-F0-9])'+re.escape(SHA[:7])+r'[a-fA-F0-9]*(?![a-fA-F0-9])', report), 'Unconfirmed full or abbreviated commit SHA leaked as report evidence'


def unavailable(report):
    assert re.search(r'unavailable|unknown|not recorded', report, re.I), 'Missing accounting became zero'


def escaped(report):
    assert '|raw|' not in report and '\n# injected' not in report, 'Markdown label injection'
    has(report, '東京')
    assert '[click](https://example.invalid)' not in report, 'Markdown link injection'
    assert '**bold**' not in report, 'Markdown emphasis injection'
    assert '`code`' not in report, 'Markdown code injection'


def plain(text):
    """Remove presentation delimiters, not content; accept lists/tables/emphasis."""
    text = re.sub(r'\\([\\`*_{}\[\]()#+.!|>-])', r'\1', text)
    return re.sub(r'[*_`|]', ' ', text).strip().lower()


def section(report, label):
    lines = report.splitlines()
    # Expand ordinary Markdown table columns into labeled values, preserving sections.
    expanded = []; headers = None
    for line in lines:
        if line.strip().startswith('|'):
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if all(re.fullmatch(r':?-{3,}:?', c) for c in cells):
                continue
            if headers is None:
                headers = cells; expanded.append(line)
            else:
                expanded.append('; '.join(h+': '+v for h,v in zip(headers,cells)))
        else:
            headers = None; expanded.append(line)
    lines = expanded
    for index, line in enumerate(lines):
        if re.match(r'^\s*#{1,6}\s+', line) and re.search(label, plain(line)):
            end = next((i for i in range(index+1, len(lines)) if re.match(r'^\s*#{1,6}\s+', lines[i])), len(lines))
            return '\n'.join(lines[index:end])
    # Inline labeled summaries are also supported.
    selected = [line for line in lines if re.search(label, plain(line))]
    assert selected, 'Missing labeled report section: '+label
    return '\n'.join(selected)


def unknown_field(report, label):
    value = section(report, label)
    unavailable(value)
    assert not re.search(r'\b0\b', plain(value)), 'Unknown field became recorded zero: '+label


def check_counts(report, total, failed):
    scope = section(report, r'checks?')
    cleaned = plain(scope)
    assert re.search(r'\b'+str(total)+r'\b', cleaned), 'Missing check count'
    assert re.search(r'(?:fail\w*[^\n]*\b'+str(failed)+r'\b|\b'+str(failed)+r'\b[^\n]*fail)', cleaned), 'Missing failed check count'
    assert re.search(r'(?:total[^\n]*\b'+str(total)+r'\b|\b'+str(total)+r'\b[^\n]*(?:total|checks?))', cleaned), 'Missing labeled total checks'


def outcome(report):
    return plain(section(report, r'\b(?:status|outcome|integration)\b'))


def integration_unconfirmed(report):
    assert re.search(r'unconfirmed|confirming|unavailable|incomplete|pending|not.confirmed', outcome(report)), 'Incorrect confirmed integration'


def integration_confirmed(report):
    value = outcome(report)
    assert re.search(r'\bmerged\b|\bintegrated\b', value)
    assert not re.search(r'unconfirmed|confirming|unavailable|incomplete|pending|not.confirmed', value)
