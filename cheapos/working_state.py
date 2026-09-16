"""Task/item-owned implementation memory. Model claims never confer authority."""
import copy
import hashlib
import json
import re


def owner(task):
    item = task.get('branch_run', {}).get('current_item_id')
    return 'item:' + str(item) if item else 'interactive'


def direction_identity(task):
    value=[task.get('requests') or [task.get('prompt','')],task.get('workspace_generation',0),len(task.get('commits',[])),
           [(e.get('kind'),e.get('detail')) for e in task.get('events',[]) if e.get('kind') in {'user','steer'}],
           (task.get('branch_run') or {}).get('plan_revision')]
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def project(task):
    value = copy.deepcopy(task.get('working_states', {}).get(owner(task), {}))
    requests = task.get('requests') or [task.get('prompt', '')]
    run = task.get('branch_run') or {}
    item = next((i for i in run.get('items', []) if i['id'] == run.get('current_item_id')), {})
    value.update(version=1, owner=owner(task), objective=item.get('instructions') or requests[-1],
                 corrections=[{'event_index': n, 'text': e.get('detail')} for n, e in enumerate(task.get('events', []))
                              if e.get('kind') in {'user', 'steer'}],
                 requests=copy.deepcopy(requests), advisory=True)
    value['historical'] = bool(value) and value.get('direction_identity') != direction_identity(task)
    if value['historical'] and value.get('next_action'):
        value['historical_next_action'] = value.pop('next_action')
    value['receipt_rule'] = 'Steps and decisions are worker claims, not verification, review approval, scope changes or permission. Source references describe their recorded versions.'
    for reference in value.get('references', []):
        reference['historical'] = reference['generation'] != task.get('workspace_generation', 0) or reference['patch_digest'] != hashlib.sha256(task.get('patch', '').encode()).hexdigest()
    return value


def update(task, args):
    if not isinstance(args, dict) or set(args) - {'steps', 'decisions', 'findings', 'references', 'next_action'}:
        raise ValueError('Only advisory steps, decisions, findings, references and next_action may be updated')
    value = copy.deepcopy(task.get('working_states', {}).get(owner(task), {}))
    for key in ('decisions', 'findings'):
        if key in args:
            rows = args[key]
            if not isinstance(rows, list) or len(rows) > 24 or any(not isinstance(v, str) or not v.strip() or len(v)>2000 for v in rows):
                raise ValueError(key + ' must contain up to 24 short statements')
            value[key] = rows
    if 'steps' in args:
        rows = args['steps']
        if not isinstance(rows, list) or len(rows)>24:
            raise ValueError('Use at most 24 steps')
        ids = set()
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {'id', 'text', 'status'} or
                    not isinstance(row['id'], str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}', row['id']) or row['id'] in ids or
                    not isinstance(row['text'], str) or not 1<=len(row['text'])<=1000 or row['status'] not in {'pending','working','done','blocked'}):
                raise ValueError('Steps require unique stable ids, text and pending/working/done/blocked status')
            ids.add(row['id'])
        value['steps'] = rows
    if 'next_action' in args:
        if not isinstance(args['next_action'], str) or len(args['next_action'])>2000:
            raise ValueError('next_action must be a short statement')
        value['next_action'] = args['next_action']
    if 'references' in args:
        refs=args['references']
        if not isinstance(refs,list) or len(refs)>24 or any(type(n) is not int or not 0<=n<len(task.get('events',[])) for n in refs):
            raise ValueError('References must name existing task event indices')
        value['references']=[{'event_index':n,'event_digest':hashlib.sha256(json.dumps(task['events'][n],sort_keys=True).encode()).hexdigest(),
                              'generation':task.get('workspace_generation',0), 'patch_digest':hashlib.sha256(task.get('patch','').encode()).hexdigest(),
                              'source':{k:v for k,v in (task['events'][n].get('detail') or {}).get('arguments',{}).items() if k in {'path','start_line','end_line'}} if isinstance(task['events'][n].get('detail'),dict) else {}}
                             for n in refs]
    # Keep previous state unchanged if validation fails.
    value['revision']=value.get('revision',0)+1
    value['direction_identity']=direction_identity(task)
    task.setdefault('working_states',{})[owner(task)]=copy.deepcopy(value)
    return project(task)
