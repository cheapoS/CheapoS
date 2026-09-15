"""Explicit operator work allowances; accounting and money caps stay enabled."""

def is_measurement(task):
    return task.get('branch_run', {}).get('plan', {}).get('measurement') is True


def enabled(task):
    # Unattended authority comes from the approved plan, never task-local flags.
    if 'branch_run' in task:
        return is_measurement(task) or task['branch_run'].get('plan', {}).get('uncapped_work') is True
    return task.get('limits', {}).get('uncapped_work') is True
