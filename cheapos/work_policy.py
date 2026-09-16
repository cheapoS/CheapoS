"""Small deterministic worker policy; no model-name or reasoning heuristics."""
import hashlib


# These are the welcome screen's operator-selected requests, not a classifier
# for arbitrary chat. A follow-up or an edited draft keeps its own meaning.
READ_ONLY_STARTERS = (
    'Explain how this project works. Start by reading its README and main entry points.',
    'Look through this project and suggest one small improvement. Explain it before making changes.',
)
READ_ONLY_TOOLS = frozenset({'list_files', 'read_file', 'outline_file', 'search',
                             'read_url', 'read_merge_context', 'get_diff', 'read_context_evidence', 'read_check_output', 'update_working_state', 'ask_user'})


class ReadOnlyViolation(ValueError):
    code = 'read_only_request'


def read_only(task):
    if not task.get('conversational') or task.get('branch_run') or task.get('demo'):
        return False
    latest = (task.get('requests') or [task.get('prompt', '')])[-1]
    return ' '.join(latest.split()).casefold() in {
        ' '.join(prompt.split()).casefold() for prompt in READ_ONLY_STARTERS}


def active_implementation(task):
    """An accepted branch item needs work even before its first edit."""
    run = task.get('branch_run') or {}
    return any(item.get('id') == run.get('current_item_id') and
               item.get('status') not in {'committed', 'satisfied_without_change'}
               for item in run.get('items', []))


def offered_tools(task, tools):
    return [tool for tool in tools if tool['function']['name'] in READ_ONLY_TOOLS] if read_only(task) else tools


def validate_response(task, message):
    """Guard the whole response before dispatch, including mixed tool batches."""
    if not read_only(task):
        return
    for call in message.get('tool_calls') or []:
        name = call.get('function', {}).get('name') if isinstance(call, dict) else None
        if name not in READ_ONLY_TOOLS:
            raise ReadOnlyViolation('This request is for an explanation or suggestion only. '
                                    'No tools from this response were executed. Answer from the files already read; '
                                    'describe any suspected bug without fixing it. Do not run tests or request review. '
                                    'Wait for the operator to ask for implementation. Do not claim checks ran.')


def small_edit_reason(task):
    if read_only(task):return None
    if task.get('compact_edits'):return None
    if stage(task)=='review':return None
    if task['limits']['output_tokens']<=768:return 'The selected output allowance is at most 768 tokens.'
    events=task.get('events',[])
    boundary=max((i for i,event in enumerate(events) if event['kind']=='user'),default=-1)
    for event in reversed(events[boundary+1:]):
        detail=event.get('detail')
        if not isinstance(detail,dict):continue
        if event['kind']=='tool_error' and detail.get('tool') in {'write_file','replace_text','replace_lines'}:
            return 'An edit-output failure was observed in this task.'
    return None


def stage(task):
    if read_only(task):return 'explanation'
    if task.get('status')=='reviewing':return 'review'
    if task.get('conversational') and not active_implementation(task) and task.get('patch', '') == task.get('turn_start_patch', ''):
        return 'orientation'
    check=(task.get('checks') or [{}])[-1]
    if task.get('changes'):
        current=hashlib.sha256(task.get('patch','').encode()).hexdigest()
        if (check.get('passed') and check.get('digest')==current and check.get('verification_identity')
                and check.get('generation',0)==task.get('workspace_generation',0)):return 'review'
        if check.get('digest') != current:
            return 'verification'
        return 'verification' if not check or check.get('passed') else 'implementation'
    # Reading is not authorization to implement. Ordinary chat retains all
    # tools, but the controller must not turn inspection into a repair order.
    if active_implementation(task):return 'implementation'
    if task.get('conversational'):return 'orientation'
    return 'implementation' if any(e['kind']=='tool' for e in task.get('events',[])) else 'orientation'


def instruction(value):
    focus={'explanation':'This is a read-only explanation or suggestion request. Read relevant files, then answer the latest question in plain text. If a README is absent, explain the files that exist. Describe suspected bugs as source observations, not executed test results. Do not edit, run tests, or submit a checkpoint. Suggestions wait for the operator to request implementation.',
           'orientation':'Use the project brief and targeted reads to answer the latest request. For questions or suggestions, give a plain-text answer without edits or checks. Only implement when the operator has requested changes.',
           'implementation':'Make the smallest sufficient complete edit, using existing project structures.',
           'verification':'Run suitable authorized checks when the requested implementation is complete; otherwise finish its remaining edits.',
           'review':'Submit the completed requested patch for review. Passing checks alone do not establish completion.'}[value]
    return f'Current stage: {value}. {focus} Preserve every active requirement. Avoid speculative abstractions and full-file prose. Read missing context with the offered tools; do not guess. Report actual evidence.'


def prioritize(tools,value):
    first={'explanation':{'read_file','outline_file','search'},'orientation':{'read_file','outline_file','search'},'implementation':{'replace_text','replace_lines','write_file'},
           'verification':{'run_checks','checkpoint'},'review':{'checkpoint','review_decision'}}[value]
    return sorted(tools,key=lambda tool:tool['function']['name'] not in first)
