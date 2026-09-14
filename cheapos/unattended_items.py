"""Pure scheduling of explicitly authorized independent work; never clears files."""
import copy
from . import branch_runs as state

ACTIVE = frozenset(('working', 'checking', 'reviewing', 'committing'))


def enabled(run):
    return run.get('plan', {}).get('continue_independent') is True


def next_item(run):
    unfinished = [item for item in run['items'] if item['status'] not in state.DONE]
    if not enabled(run):
        return next(iter(unfinished), None)
    active = next((item for item in unfinished if item['status'] in ACTIVE), None)
    if active is not None:
        return active
    done = {item['id'] for item in run['items'] if item['status'] in state.DONE}
    return next((item for item in unfinished if not item.get('question')
                 and set(item['dependencies']).issubset(done)), None)


def defer(run, item, question, clean):
    """Caller verifies clean workspace and holds controller lock before mutation."""
    if not enabled(run) or clean is not True or run.get('pending_operations'):
        return False
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        return False
    if not any(candidate is item for candidate in run['items']) or item['status'] in state.DONE:
        return False
    trial = copy.deepcopy(run)
    blocked = next(candidate for candidate in trial['items'] if candidate['id'] == item['id'])
    blocked.update(status='blocked', question=question)
    if next_item(trial) is None:
        return False
    state.transition_item(run, item['id'], 'blocked')
    item['question'] = question
    run.pop('waiting_for_user', None)
    run['current_item_id'] = None
    return True


def completion_order(run):
    """Bind final receipt-chain traversal to the durable actual execution order."""
    if not enabled(run):
        return run['items']
    items = {item['id']: item for item in run['items']}
    operations = run.get('completed_operations', [])
    if len(items) != len(run['items']) or not isinstance(operations, list) or len(operations) != len(items):
        raise ValueError('Completed operations must cover every item exactly once')
    ordered, done = [], set()
    for operation in operations:
        if not isinstance(operation, dict):
            raise ValueError('Invalid completed operation')
        item_id = operation.get('item_id')
        if item_id not in items or item_id in done:
            raise ValueError('Completed operations contain unknown or duplicate items')
        item = items[item_id]
        if operation.get('stage') != 'completed' or operation.get('run_id') != run['id'] or operation != item.get('commit_receipt'):
            raise ValueError('Completed operation differs from the item receipt')
        if not set(item['dependencies']).issubset(done):
            raise ValueError('Completed operation precedes its dependencies')
        ordered.append(item)
        done.add(item_id)
    return ordered
