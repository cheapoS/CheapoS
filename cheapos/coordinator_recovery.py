"""Bounded, untrusted recovery evidence and strict advice; never executes advice."""
from .instructions.runtime import prompt as instruction_prompt
import hashlib
import json
import re
from pathlib import PurePosixPath
from .progress import digest
from .workspace import Workspace, allowed_name
from .work_policy import read_only

MAX_PACKET = 16000
MAX_RESPONSE = 2048
SYSTEM = instruction_prompt('coordinator_recovery')

PATH_REFERENCES = re.compile(r'(?<![\w/\\])(?:\.\./|/)?(?:[\w.-]+/)+[\w.-]+|(?<![\w/\\])[\w.-]+\.(?:py|js|ts|tsx|jsx|json|md|html|css|sh|yaml|yml|toml|txt|log)\b')


def scope_paths(supplied):
    """Advisory references from accepted scope, never from repository/model text."""
    sources = supplied.get('instruction_sources', {})
    item = sources.get('accepted_item')
    scope = item if item else sources.get('operator', {})
    fields = ('title', 'instructions', 'acceptance_criteria') if item else ('original', 'latest', 'steering')
    paths = []
    for field in fields:
        value = scope.get(field, '')
        text = value if isinstance(value, str) else json.dumps(value)
        for match in PATH_REFERENCES.finditer(text):
            path = match.group().rstrip('.')
            relative = PurePosixPath(path)
            if (path and not relative.is_absolute() and '..' not in relative.parts
                    and allowed_name(path) and path not in paths):
                paths.append(path)
    return paths


class FormatError(ValueError):
    code = 'coordinator_format'


class PathReferenceError(ValueError):
    code = 'coordinator_path_reference'


def episode_key(task):
    run = task.get('branch_run') or {}
    segment = ['item', run.get('current_item_id')] if run else ['request', len(task.get('requests') or [task.get('prompt', '')])]
    return digest([task.get('id'), segment])


def recovery_evidence(task):
    """Stable work evidence; reads, clocks, usage and retries do not renew help."""
    check = (task.get('checks') or [{}])[-1]
    review = (task.get('checkpoints') or [{}])[-1]
    return {'patch': digest(task.get('patch') or ''),
            'check': {k: check[k] for k in ('command', 'digest', 'passed', 'outcome', 'exit_code') if k in check},
            'review': {k: review[k] for k in ('candidate_id', 'decision', 'feedback') if k in review}}


def current_episode(task):
    key = episode_key(task)
    evidence = recovery_evidence(task)
    for episode in reversed(task.get('coordinator_recovery', [])):
        if episode.get('key') != key:
            continue
        if 'work_evidence' in episode:
            if episode['work_evidence'] == evidence:
                return episode
            continue
        # Legacy packets can prove that a *different candidate* was checked.
        # With no reliable baseline, retain the previous attempt conservatively.
        prior = next((e for e in episode.get('packet', {}).get('evidence', [])
                      if e.get('kind') == 'last_verification'), None)
        try:
            saved = json.loads(prior['text']) if prior else {}
        except (ValueError, TypeError, KeyError):
            saved = {}
        now = evidence['check']
        if saved.get('digest') and now.get('digest') and saved['digest'] != now['digest']:
            continue
        return episode
    return None


def identity(task):
    run = task.get('branch_run') or {}
    return digest({'episode': episode_key(task), 'requests': task.get('requests'), 'prompt': task.get('prompt'),
                   'patch': task.get('patch'), 'generation': task.get('workspace_generation'),
                   'authority': run.get('authorization'), 'inputs': run.get('inputs'),
                   'plan': run.get('plan'), 'limits': task.get('limits'), 'workspace': task.get('workspace'),
                   'pending_approval': task.get('pending_approval'), 'waiting_for_user': run.get('waiting_for_user'),
                   'execution': task.get('execution'), 'read_only': read_only(task),
                   'item_scope': next((item for item in run.get('items', []) if item.get('id') == run.get('current_item_id')), None),
                   'check_candidate': (task.get('checks') or [{}])[-1], 'guidance': task.get('steer_guidance'), 'branch_guidance': run.get('guidance')})


def _text(value, maximum):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True, sort_keys=True)
    return text if len(text) <= maximum else text[:maximum] + ' [omitted]'


def progress_evidence(task):
    """Useful patch/review content before bulky historical packets or hashes."""
    review = (task.get('checkpoints') or [{}])[-1]
    sections = re.split(r'(?=^diff --git )', task.get('patch') or '', flags=re.M)
    sections = [section for section in sections if section.strip()]
    return {'last_review': {key: _text(review[key], cap) for key, cap in
                           (('decision', 80), ('feedback', 1800), ('worker_summary', 400)) if key in review},
            'current_patch': [_text(section, 900) for section in sections[:4]],
            'patch_omitted': len(sections) > 4}


def excerpt_start(task, name):
    section = next((s for s in re.split(r'(?=^diff --git )', task.get('patch') or '', flags=re.M)
                    if re.search(r'^\+\+\+ b/' + re.escape(name) + r'$', s, re.M)), '')
    starts = re.findall(r'^@@ -\d+(?:,\d+)? \+(\d+)', section, re.M)
    return max(1, int(starts[-1])) if starts else 1


def packet(engine, runtime, reason):
    task = runtime.task
    run = task.get('branch_run') or {}
    item = next((i for i in run.get('items', []) if i.get('id') == run.get('current_item_id')), None)
    result = {'schema_version': 1, 'episode': episode_key(task), 'identity': identity(task),
              'instruction_sources': {'operator': {'original': _text(task.get('prompt', ''), 1400), 'latest': _text((task.get('requests') or [task.get('prompt', '')])[-1], 1400), 'steering': _text(task.get('steer_guidance') or run.get('guidance') or '', 700), 'intermediate_messages': 'Omitted; original and latest operator scope retained'},
                                      'accepted_item': {key: _text((item or {}).get(key), cap) for key, cap in (('id',100),('title',200),('instructions',1200),('acceptance_criteria',1600),('required_checks',600),('review_repair',700))} if item else {}},
              'read_only': read_only(task), 'stall': _text(str(reason), 1200),
              'constraints': {'pending_approval': bool(task.get('pending_approval')), 'waiting_for_user': bool(run.get('waiting_for_user')),
                              'limits': task.get('limits', {}), 'usage': task.get('usage', {}),
                              'branch_remaining': {k: max(0, v - run.get('consumption', {}).get(k, 0)) for k, v in run.get('limits', {}).items() if type(v) in (int, float)}},
              'evidence': [], 'permitted_paths': [], 'scope_paths': [], 'observed_ranges': {}, 'omitted': []}
    def add(kind, value, maximum=1200):
        result['evidence'].append({'id': 'e' + str(len(result['evidence']) + 1), 'kind': kind, 'text': _text(value, maximum)})
    add('observed_stall', str(reason))
    if task.get('syntax_edit_recovery'):
        from .edit_recovery import syntax_records
        add('rejected_edits', [{'path': path, 'attempts': row['attempts'], 'error': row['warning'],
                               'file_preserved': True} for path, row in syntax_records(task).items()], 1600)
    add('saved_changes', [{'path': c.get('path'), 'hash': c.get('hash')} for c in task.get('changes', [])], 1800)
    if task.get('checks'):
        check = task['checks'][-1]
        verification = {k: check[k] for k in ('passed', 'command', 'outcome', 'digest') if k in check}
        output = str(check.get('output') or '')
        # Test runners usually print passing cases first and the failure at the
        # end. Preserve the actionable failure, not just the first passing lines.
        verification['output'] = output[-2400:] if not check.get('passed') else _text(output, 700)
        add('last_verification', verification, 3200)
    evidence = progress_evidence(task)
    if evidence['last_review']: add('last_review', evidence['last_review'], 2500)
    if evidence['current_patch']: add('current_patch', {k:v for k,v in evidence.items() if k != 'last_review'}, 4200)
    for key in ('pending_review', 'review_findings', 'loop_guidance', 'output_recovery', 'progress_state'):
        if task.get(key): add(key, task[key], 700)
    recent = [e for e in task.get('events', []) if e.get('kind') in {'tool', 'tool_error', 'check', 'review', 'guard', 'error'}][-5:]
    for event in recent: add('recent_action', {k: event.get(k) for k in ('kind', 'title', 'detail')}, 500)
    workspace = Workspace(task['workspace'])
    for name in scope_paths(result):
        try: workspace.path(name)
        except (OSError, ValueError): continue
        result['scope_paths'].append(name)
    try:
        # Existing bounded tracked/untracked index, with Workspace path checks.
        names = workspace.list_files()
        relevant = [c.get('path') for c in task.get('changes', [])] + [name for name, _ in getattr(runtime, 'file_observations', {})]
        # Runtime observations disappear on restart/handoff. Recover relevant
        # paths from saved tool metadata, never from arbitrary model prose.
        for event in reversed(task.get('events', [])):
            detail = event.get('detail')
            if event.get('kind') not in {'tool', 'tool_error'} or not isinstance(detail, dict):
                continue
            for field in ('result', 'arguments'):
                value = detail.get(field)
                if isinstance(value, dict) and isinstance(value.get('path'), str):
                    relevant.append(value['path'])
        relevant = list(dict.fromkeys(name for name in relevant if name in names))
        indexed = list(dict.fromkeys([name for name in result['scope_paths'] if name in names] + relevant + names))
        for name in indexed[:100]:
            try: workspace.path(name)
            except ValueError: continue
            if len(name) <= 180: result['permitted_paths'].append(name)
        if len(names) > len(result['permitted_paths']): result['omitted'].append('Some file-index entries omitted')
        for name in relevant[:3]:
            if name not in result['permitted_paths']: continue
            try:
                start = excerpt_start(task, name)
                file = workspace.read_file(name, start, start + 49)
                add('current_file', file.get('content', ''), 1100)
                result['evidence'][-1].update({key: file.get(key) for key in ('path', 'hash', 'start_line', 'end_line')})
                observed = getattr(runtime, 'file_observations', {}).get((name, file.get('hash')), {}).get('lines', set())
                ranges = []
                for line in sorted(n for n in observed if type(n) is int and n >= 1):
                    if ranges and line == ranges[-1][1] + 1: ranges[-1][1] = line
                    else: ranges.append([line, line])
                if type(file.get('start_line')) is int and type(file.get('end_line')) is int:
                    visible_end = file['end_line'] if len(file.get('content', '')) <= 1100 else file['start_line'] + file['content'][:1100].count('\n') - 1
                    if visible_end >= file['start_line']: ranges.append([file['start_line'], visible_end])
                result['observed_ranges'][name] = ranges[:10]
            except (OSError, ValueError): result['omitted'].append('Current excerpt unavailable: ' + name)
    except (OSError, ValueError):
        result['omitted'].append('File index unavailable; absence is not proof of missing code')
    # Retain scope/stall first, drop oldest optional action/file evidence as needed.
    while len(json.dumps(result)) > MAX_PACKET and len(result['evidence']) > 2:
        result['evidence'].pop()
        result['omitted'] = ['Optional evidence omitted to fit packet limit']
    while len(json.dumps(result)) > MAX_PACKET and result['permitted_paths']:
        result['permitted_paths'].pop()
    if len(json.dumps(result)) > MAX_PACKET:
        result['constraints'] = {'pending_approval': bool(task.get('pending_approval')), 'allowances': 'Details omitted; existing engine limits still apply'}
    if len(json.dumps(result)) > MAX_PACKET:
        raise ValueError('Recovery evidence exceeds the bounded packet contract')
    return result


def validate(response, supplied, workspace=None):
    if isinstance(response, str):
        # A single complete Markdown wrapper adds no authority. The object still
        # passes every schema, evidence and policy check; prose is not extracted.
        fenced = re.fullmatch(r'\s*```(?:json)?\s*\n(.*?)\n```\s*', response, re.S)
        if fenced: response = fenced.group(1)
        if len(response) > MAX_RESPONSE: raise ValueError('Coordinator response is too large')
        try: value = json.loads(response)
        except (ValueError, TypeError): raise FormatError('Coordinator must return one JSON object') from None
    else: value = response
    if not isinstance(value, dict) or len(json.dumps(value)) > MAX_RESPONSE:
        raise ValueError('Coordinator must return a bounded object')
    schemas = {'continue': {'action', 'next_step', 'expected_result'},
               'need_context': {'path', 'start_line', 'end_line', 'reason', 'decision'},
               'suggest_handoff': {'reason', 'brief'}, 'needs_user': {'question', 'reason'},
               'unresolved': {'blocker', 'failed_approach'}}
    outcome = value.get('outcome')
    if not isinstance(outcome, str) or outcome not in schemas or set(value) != schemas[outcome] | {'outcome', 'evidence'}:
        raise ValueError('Unknown coordinator outcome or fields')
    refs = value['evidence']
    valid_refs = {e['id'] for e in supplied.get('evidence', [])}
    if not isinstance(refs, list) or not 1 <= len(refs) <= 8 or any(not isinstance(ref, str) or ref not in valid_refs for ref in refs):
        raise ValueError('Advice must reference supplied evidence')
    for key in schemas[outcome] - {'start_line', 'end_line'}:
        text = value[key]
        if not isinstance(text, str) or not text.strip() or len(text) > 900:
            raise ValueError('Advice requires specific bounded text')
        if key not in {'action', 'path'} and (len(text.split()) < 4 or re.fullmatch(r'(try harder|continue working|try again|keep going)[.! ]*', text, re.I)):
            raise ValueError('Generic coordinator guidance is not actionable')
        if re.search(r'(?i)(skip|bypass|disable|ignore)\s+(the\s+)?(tests?|checks?|approvals?|permissions?|review)|increase\s+(the\s+)?(budget|allowance)|```|\b(rm -rf|curl |sudo )', text):
            raise ValueError('Advice cannot bypass policy or provide commands')
    # File references need supplied evidence. An unambiguous basename is normal
    # prose; a described /api/... route is not a filesystem read/write target.
    # Derive scope references from the saved instructions as well, so a retained
    # reply rejected by the old existing-files-only rule can be reused without
    # another inference call. These references grant no tool/write authority.
    allowed_paths = set(supplied.get('permitted_paths', [])) | set(scope_paths(supplied))
    for key in schemas[outcome] - {'start_line', 'end_line', 'action', 'path'}:
        text = value[key]
        paths = PATH_REFERENCES.finditer(text)
        for match in paths:
            path = match.group()
            if path not in allowed_paths:
                path = path.rstrip('.')  # Sentence punctuation in prose, not a typed path.
            if path not in allowed_paths and '/' not in path:
                matches = [p for p in allowed_paths if PurePosixPath(p).name == path]
                if len(matches) == 1: path = matches[0]
            if path in allowed_paths:
                if workspace is not None: workspace.path(path)
                continue
            # Only a clearly described API route, with no traversal/file suffix,
            # qualifies. Typed need_context.path remains strictly workspace-bound.
            # API verbs can precede the URL by a clause ("polls until the server
            # returns 200 OK on ..."). Do not cut that context at 40 characters.
            around = text
            if (path.startswith('/api/') and not any(part in {'.','..'} for part in path.split('/'))
                    and '.' not in path and re.search(r'\b(route|endpoint|GET|POST|PUT|PATCH|DELETE|HTTP|poll(?:s|ing)?|fetch)\b', around, re.I)):
                continue
            raise PathReferenceError('Advice references a path outside supplied evidence: ' + path)
        if supplied.get('read_only') and re.search(r'(?:^|[.!;]\s+|\band then\s+)(?:please\s+)?(?:edit|modify|write|replace|delete|create|remove|run|execute|commit|merge)\b', text, re.I):
            raise ValueError('Read-only advice cannot direct a modifying action')
    if outcome == 'continue':
        if value['action'] not in {'inspect', 'edit', 'check', 'answer'}:
            raise ValueError('Unknown continuation action')
        if supplied.get('read_only') and value['action'] not in {'inspect', 'answer'}:
            raise ValueError('Read-only scope cannot authorize implementation')
        if supplied.get('constraints', {}).get('pending_approval'):
            raise ValueError('Pending permission cannot be resolved by coordinator advice')
    if outcome == 'need_context':
        path = value['path']; relative = PurePosixPath(path)
        if path not in supplied.get('permitted_paths', []) or relative.is_absolute() or '..' in relative.parts or '\\' in path or '\x00' in path:
            raise ValueError('Context path is outside supplied permitted evidence')
        start, end = value['start_line'], value['end_line']
        if type(start) is not int or type(end) is not int or not 1 <= start <= end or end - start >= 300:
            raise ValueError('Context range must be at most 300 lines')
        if any(low <= start and high >= end for low, high in supplied.get('observed_ranges', {}).get(path, [])):
            raise ValueError('Requested context repeats already available evidence')
    return dict(value)


def evidence_current(runtime, supplied):
    """Recheck bounded current-file snapshots before applying late advice."""
    workspace = Workspace(runtime.task['workspace'])
    for entry in supplied.get('evidence', []):
        if entry.get('kind') != 'current_file': continue
        try:
            actual = hashlib.sha256(workspace.text_bytes(entry['path'])).hexdigest()
        except (OSError, ValueError, KeyError): return False
        if actual != entry.get('hash'): return False
    return True
