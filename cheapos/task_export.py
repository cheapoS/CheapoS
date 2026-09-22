"""Operator-facing task summary; not a backup or signed statistics submission."""


def summary(task):
    def fields(value, names):
        return {name: value[name] for name in names if name in value}
    result = fields(task, ('id', 'title', 'prompt', 'requests', 'created_at', 'updated_at',
                           'status', 'usage', 'session_actions', 'metrics'))
    result.update(schema_version=1, kind='task_summary',
                  scope='Local task summary. May contain private task text; not signed public statistics or a resumable backup.')
    result['steps'] = []
    for event in task.get('events', []):
        if event.get('kind') in {'model', 'routing', 'generation', 'planning_repair'}:
            continue
        step = fields(event, ('id', 'time', 'kind', 'title', 'actor', 'item_id'))
        detail = event.get('detail')
        if isinstance(detail, str):
            step['summary'] = detail
        elif isinstance(detail, dict):
            step['result'] = fields(detail, ('path', 'summary', 'message', 'decision', 'passed', 'error'))
        result['steps'].append(step)
    result['checks'] = [fields(check, ('id', 'command', 'commands', 'directory', 'passed', 'outcome', 'exit_code'))
                        for check in task.get('checks', [])]
    result['checkpoints'] = [fields(review, ('number', 'decision', 'worker_summary', 'feedback', 'uncertainties'))
                             for review in task.get('checkpoints', [])]
    result['changes'] = [fields(change, ('path', 'status')) for change in task.get('changes', [])]
    if task.get('branch_run'):
        from .branch_runs import summary as branch_summary
        result['branch_run'] = branch_summary(task['branch_run'])
    return result
