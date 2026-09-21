"""Optional agent publication copy, bound to existing review evidence.

Missing/invalid prose never blocks implementation or starts a model request.
Only controller-recorded checks populate the separate validation section.
"""
import re
import shlex

SCHEMA = {'type': 'object', 'properties': {
    'title': {'type': 'string', 'maxLength': 200, 'description': 'Concrete change and resulting behavior.'},
    'description': {'type': 'string', 'maxLength': 6000, 'description': 'What changed, why, and remaining limitations. No invented checks, links, or approval claims.'}},
    'required': ['title', 'description'], 'additionalProperties': False}

WORKER = ('This task uses the GitHub PR workflow. When calling checkpoint after implementation, include optional '
          'pull_request: {title, description}. Describe the actual completed change, why it helps, and remaining '
          'limitations for a reader who has not seen this chat. Refresh it after repairs; do not repeat the original '
          'request or abandoned approaches. For an unattended item describe that item; final review combines the items. '
          'Do not include private links, local machine paths, secrets, or unverified claims. The controller adds '
          'recorded validation separately. This is metadata, not a request to publish or another implementation step.')
REVIEW = (' Review the supplied pull_request_draft against the actual diff and evidence. On APPROVE, include optional '
          'pull_request: {title, description} with confirmed or corrected wording. Remove unsupported claims and '
          'outdated scope. Do not request code changes only to improve PR wording; correct it in your decision. '
          'Omit metadata if you cannot support it. The controller supplies validation from saved checks.')
FINAL = (' On final synthesis APPROVE, also return optional pull_request: {title, description} summarizing the '
         'whole final change using the current evidence and publication_drafts (historical item summaries, not '
         'requirements). Correct stale claims after repairs. Include why and any limitations; omit private links, '
         'machine paths and unsupported claims. The controller supplies recorded validation. Omit metadata if '
         'unsupported; missing PR prose must not reject otherwise valid work.')


def enabled(task):
    return task.get('settings_snapshot', {}).get('values', {}).get('git', {}).get('workflow') == 'pull_request'


def clean(value):
    if not isinstance(value, dict) or set(value) != {'title', 'description'}:
        return None
    if not all(isinstance(value.get(k), str) for k in ('title', 'description')):
        return None
    title, description = value['title'].strip(), value['description'].strip()
    if not title or len(title) > 200 or len(description) > 6000 or '\n' in title or '\r' in title:
        return None
    if re.search(r'[\x00-\x08\x0b-\x1f\x7f]', title + description):
        return None
    return {'title': title, 'description': description}


def item_drafts(manifest):
    drafts = []
    for entry in manifest.get('requirements', []) + manifest.get('repair_evidence', []):
        value = clean(entry.get('review', {}).get('pull_request'))
        if value and value not in drafts:
            drafts.append(value)
    return drafts


def preview(task, candidate):
    run = task.get('branch_run')
    if run:
        ready = run['readiness']
        review = ready['review']
        records = [row['record'] for row in ready['checks']]
    else:
        review = (task.get('checkpoints') or [{}])[-1]
        records = [review['checks']] if review.get('checks') else []
    draft = clean(review.get('pull_request')) if review.get('decision') == 'APPROVE' else None
    if not draft:
        title = re.sub(r'\s+', ' ', task.get('title') or 'Update project')[:200]
        files = candidate.get('files', [])
        draft = {'title': title, 'description': 'Updates ' + str(len(files)) + ' file(s) in the reviewed change.'}
    rows = []
    for record in records:
        # Candidate admission already verifies identity. Never promote historical
        # failures, truncated output or model-authored test claims into success.
        if record.get('passed') is not True or record.get('exit_code') != 0 or record.get('truncated') or record.get('reason') or record.get('outcome', 'passed') != 'passed':
            continue
        command = record.get('command', [])
        command = shlex.join(command) if isinstance(command, list) else str(command)
        directory = record.get('directory', '.')
        row = f'- Passed: {command} (directory: {directory}; exit 0)'
        if row not in rows:
            rows.append(row)
    validation = '\n'.join(rows) if rows else 'No individual check details are available in this saved publication record.'
    return {**draft, 'validation': validation, 'description_source': 'reviewer' if clean(review.get('pull_request')) else 'fallback'}


def body(operation):
    return ('## Changes\n\n' + operation.get('description', operation['message']) + '\n\n## Recorded validation\n\n'
            + operation.get('validation', 'Individual check details were not retained in this older publication.')
            + '\n\nIndependent cheapoS review approved this candidate. Published commit: `' + operation['head'] + '`.\n'
              'Review the diff and GitHub CI results before merging.\n\nCreated by cheapoS.')
