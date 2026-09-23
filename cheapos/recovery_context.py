"""Bounded continuation evidence; prior model statements are not verification."""
from .instructions.runtime import text as instruction
import hashlib
from .worker_context import active_events

TEST_POLICY = instruction('validation.recovery')


def packet(task):
    run = task.get('branch_run') or {}
    guidance = [g.get('message', '') for g in run.get('guidance', [])
                if g.get('item_id') == run.get('current_item_id')]
    latest = task.get('steer_guidance') or (guidance[-1] if guidance else
              (task.get('requests') or [task.get('prompt', '')])[-1])
    statements = []
    seen = set()
    for event in reversed(active_events(task)):
        if event.get('kind') != 'assistant' or not isinstance(event.get('detail'), str):
            continue
        text = event['detail'][:1800]
        if text in seen:
            continue
        seen.add(text)
        statements.append(text)
        if len(statements) == 3:
            break
    checks = [{k: check[k] for k in ('command', 'passed', 'exit_code', 'digest', 'verification_identity', 'generation') if k in check}
              for check in task.get('checks', [])[-4:]]
    current = next((check for check in reversed(task.get('checks', []))
                    if check.get('passed') and check.get('digest') == hashlib.sha256(task.get('patch', '').encode()).hexdigest()
                    and check.get('verification_identity') and check.get('generation', 0) == task.get('workspace_generation', 0)), None)
    next_step = ('A check passed for this patch and workspace generation. Verify its input identity and command coverage; '
                 'if it satisfies the item, submit checkpoint for independent review. Do not restart discovery.' if current else
                 'Use the findings and current files to choose the smallest missing verification step. '
                 'Inspect the exact failed assertion or run a focused check; avoid rereading unchanged files.')
    from .working_state import project
    from .edit_recovery import repair_packet
    working = project(task)
    if working.get('next_action'): next_step = working['next_action']
    return {'working_state': working, 'edit_recovery': repair_packet(task), 'latest_operator_direction': latest[:8000], 'prior_worker_statements_unverified': list(reversed(statements)),
            'completed_items': [{'id': item['id'], 'summary': item.get('outcome_summary', '')[:800]}
                                for item in run.get('items', []) if item.get('status') in {'committed', 'satisfied_without_change'}][-12:],
            'recent_check_receipts': checks, 'next_step': next_step, 'validation_policy': TEST_POLICY,
            'evidence_rule': 'Model statements and completed-item summaries are historical claims, not proof that all tests pass. Current check evidence remains subject to identity validation.'}
