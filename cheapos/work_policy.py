"""Small deterministic worker policy; no model-name or reasoning heuristics."""
import hashlib


def small_edit_reason(task):
    if task.get('compact_edits'):return None
    if task['limits']['output_tokens']<=768:return 'The selected output allowance is at most 768 tokens.'
    events=task.get('events',[])
    boundary=max((i for i,event in enumerate(events) if event['kind']=='user'),default=-1)
    for event in reversed(events[boundary+1:]):
        detail=event.get('detail')
        if not isinstance(detail,dict):continue
        if event['kind']=='tool_error' and detail.get('tool') in {'write_file','replace_text','replace_lines'}:
            return 'An edit-output failure was observed in this task.'
        if event['kind']=='tool' and event['title']=='read file':
            result=detail.get('result') or {};result=result.get('observation',result)
            if result.get('total_lines',0)>200 or len(result.get('content',''))>6000:
                return 'An observed file exceeds 200 lines or its excerpt exceeds 6,000 characters.'
    return None


def stage(task):
    if task.get('status')=='reviewing':return 'review'
    check=(task.get('checks') or [{}])[-1]
    if task.get('changes'):
        current=hashlib.sha256(task.get('patch','').encode()).hexdigest()
        if (check.get('passed') and check.get('digest')==current and check.get('verification_identity')
                and check.get('generation',0)==task.get('workspace_generation',0)):return 'review'
        return 'verification' if not check or check.get('passed') else 'implementation'
    return 'implementation' if any(e['kind']=='tool' for e in task.get('events',[])) else 'orientation'


def instruction(value):
    focus={'orientation':'Use the project brief and targeted reads to locate the relevant code and tests.',
           'implementation':'Make the smallest sufficient complete edit, using existing project structures.',
           'verification':'Run suitable authorized checks when the requested implementation is complete; otherwise finish its remaining edits.',
           'review':'Submit the completed requested patch for review. Passing checks alone do not establish completion.'}[value]
    return f'Current stage: {value}. {focus} Preserve every active requirement. Avoid speculative abstractions and full-file prose. Read missing context with the offered tools; do not guess. Report actual evidence.'


def prioritize(tools,value):
    first={'orientation':{'read_file','outline_file','search'},'implementation':{'replace_text','replace_lines','write_file'},
           'verification':{'run_checks','checkpoint'},'review':{'checkpoint','review_decision'}}[value]
    return sorted(tools,key=lambda tool:tool['function']['name'] not in first)
