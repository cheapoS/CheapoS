"""Explicit operator development policy; no inferred opt-in or budget mutation."""


def enabled(task):
    execution=task.get('execution') or {}
    if execution.get('development_mode') is not True:
        return False
    run=task.get('branch_run')
    if not isinstance(run,dict) or not run.get('authorization_ref'):
        return True
    authorization=run.get('authorization') or {}
    contract=authorization.get('contract') or {}
    if (contract.get('model_policy') or {}).get('execution',{}).get('development_mode') is True:
        return True
    # Existing runs require an explicit receipt tied to their actual authority.
    receipt=run.get('development_authorization') or {}
    if receipt.get('enabled') is not True or receipt.get('authorization_ref')!=run.get('authorization_ref'):
        return False
    from .branch_authorization import digest
    try:return receipt.get('plan_digest')==digest(contract['plan'])
    except (KeyError,TypeError,ValueError):return False
