"""Explicit operator-selected measurement runs; accounting remains enabled."""

def enabled(task):
    return task.get('branch_run', {}).get('plan', {}).get('measurement') is True
