"""Explicit runtime prompt profiles backed by the instruction catalog.

Profiles select policies, never tools or authority. The controller still owns
tool schemas, command grants, budgets, review evidence and execution decisions.
"""
import copy
import json

from .catalog import DEFAULT_CATALOG
from .resolver import is_full_suite_authorized, resolve_rules


PROFILES = {
    'worker': ('workflow.worker_base', 'workflow.ui_completeness', 'git.internal.interactive_commit_guidance', 'recovery.edit_guidance'),
    'unattended': ('workflow.worker_base', 'workflow.ui_completeness', 'git.internal.controller_owns_commits',
                   'workflow.unattended_policy', 'workflow.unattended_blocker', 'recovery.edit_guidance'),
    'interactive': ('workflow.chat_base', 'workflow.ui_completeness', 'recovery.edit_guidance'),
    'planner': ('planner.base',),
    'reviewer': ('reviewer.base', 'workflow.ui_completeness', 'reviewer.decisions'),
    'final_review': ('reviewer.final', 'workflow.ui_completeness'),
    'review_unit': ('reviewer.unit', 'workflow.ui_completeness'),
    'review_reassessment': ('reviewer.reassessment',),
    'review_progress': ('reviewer.progress',),
    'final_review_progress': ('reviewer.progress',),
    'review_decision_coaching': ('reviewer.decision_coaching',),
    'coordinator_recovery': ('coordinator.base',),
    'coordinator_chat': ('coordinator.chat',),
    'discussion': ('conversation.discussion',),
    'greeting': ('conversation.greeting',),
    'startup_greeting': ('conversation.startup',),
}

# Tested against controller-built tool sets. These are audit expectations, not
# a tool registry or an instruction to add missing capabilities at runtime.
REQUIRED_TOOLS = {
    'worker': {'checkpoint', 'run_checks'},
    'unattended': {'checkpoint', 'run_checks', 'report_blocker'},
    'interactive': {'checkpoint', 'run_checks', 'ask_user'},
    'planner': {'inspect_project_file', 'propose_branch_plan'},
    'reviewer': {'review_decision'},
    'final_review': {'final_review_decision', 'read_final_context'},
    'review_unit': {'final_review_decision', 'read_final_context', 'read_review_evidence', 'record_review_progress'},
    'review_reassessment': {'review_decision'},
    'review_progress': {'review_decision', 'record_review_progress', 'read_review_evidence'},
    'final_review_progress': {'final_review_decision', 'record_review_progress', 'read_review_evidence'},
    'review_decision_coaching': {'review_decision'},
    'coordinator_chat': {'delegate_work'},
}
ONLY_TOOLS = {
    'planner': REQUIRED_TOOLS['planner'],
    'coordinator_chat': {'delegate_work'},
    'coordinator_recovery': set(), 'greeting': set(), 'startup_greeting': set(),
    'discussion': {'list_files', 'read_file', 'search', 'outline_file'},
    'review_decision_coaching': {'review_decision', 'read_review_evidence', 'record_review_progress'},
}


def audit_tools(profile, tools):
    """Development check only; never stops a user's run or expands its tools."""
    names = {tool['function']['name'] for tool in tools}
    errors = ['Missing offered tool: ' + name for name in sorted(REQUIRED_TOOLS.get(profile, set()) - names)]
    if profile in ONLY_TOOLS:
        errors.extend('Unexpected offered tool: ' + name for name in sorted(names - ONLY_TOOLS[profile]))
    return errors


def text(rule_id):
    rule = DEFAULT_CATALOG.get(rule_id)
    if rule is None:
        raise ValueError('Unknown instruction rule: ' + rule_id)
    return rule.text


def profile_rules(name):
    ids = PROFILES[name]
    rules = [DEFAULT_CATALOG.get(key) for key in ids]
    if any(rule is None for rule in rules):
        raise ValueError('Unknown instruction in runtime profile: ' + name)
    # Preserve deliberate prompt order after resolving declared conflicts.
    active = {rule.id for rule in resolve_rules(rules)}
    return [rule for rule in rules if rule.id in active]


def prompt(name):
    return '\n'.join(rule.text for rule in profile_rules(name))


def validation(task):
    return text('validation.full_suite_mandatory' if is_full_suite_authorized(task)
                else 'validation.change_scoped')


TOOL_CONTRACT = '\n\nCurrent tool contract:\n'


def with_tools(messages, tools, tool_choice=None):
    """Refresh one ephemeral contract after controller tool filtering.

    Do not save another history entry, overwrite user messages, raise on ordinary
    model failures, or grant missing tools to satisfy prose. Schemas are the source
    of truth for current availability and decision enums, including forced calls.
    """
    offered = {tool['function']['name']: tool['function'] for tool in tools}
    contract = {'available_tools': list(offered), 'decision_values': {}}
    for name, function in offered.items():
        choices = function.get('parameters', {}).get('properties', {}).get('decision', {}).get('enum')
        if choices:
            contract['decision_values'][name] = choices
    if isinstance(tool_choice, dict):
        required = tool_choice.get('function', {}).get('name')
        if required in offered:
            contract['required_call'] = required
    elif tool_choice == 'required' and offered:
        contract['tool_call_required'] = True
    content = TOOL_CONTRACT + text('runtime.tool_contract') + '\n' + json.dumps(contract)
    result = copy.deepcopy(messages)
    if result and result[0].get('role') == 'system':
        previous = result[0].get('content', '')
        base = '' if previous.startswith(TOOL_CONTRACT.lstrip()) else previous.split(TOOL_CONTRACT, 1)[0]
        result[0]['content'] = base + content if base else content.lstrip()
    else:
        result.insert(0, {'role': 'system', 'content': content.lstrip()})
    return result
