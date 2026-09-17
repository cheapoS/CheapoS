"""Behavior modes do not grant authority or change the chat's saved UI flag."""


def mode(task, role=None, purpose=None):
    if role == 'reviewer' or task.get('status') == 'reviewing':
        return 'review'
    if purpose == 'vision':
        return 'vision'
    run = task.get('branch_run')
    if run:
        return 'unattended' if run.get('authorization_ref') else 'planning'
    if purpose == 'branch_planning':
        return 'planning'
    return 'interactive' if task.get('conversational') else 'worker'


def guidance(task, text):
    if mode(task) == 'unattended' and isinstance(text, str):
        return text.replace('ask_user', 'report_blocker').replace(
            'For a question, give your answer now without editing files.',
            'Text alone never completes an unattended item; finish its approved acceptance criteria.')
    return text


def blocker(args):
    result = {}
    for key in ('question', 'inspected_evidence', 'why_blocked'):
        value = args.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 4000:
            raise ValueError('A blocker requires question, inspected_evidence and why_blocked, each 1–4,000 characters.')
        result[key] = value.strip()
    return result
