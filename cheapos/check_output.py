"""Optional conservative unittest summaries with bounded, task-owned raw evidence."""
import copy
import json
import os
import re
from pathlib import Path

RAW_LIMIT = 2_000_000
KEEP_RUNS = 8
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
PASS_LINE = re.compile(r'^test\S* \([^\n]+\) \.\.\. ok\s*$')
RUN_SUMMARY = re.compile(r'^Ran \d+ tests? in [\d.]+s$', re.M)


def retain(root, task_id, run_id, data, truncated):
    if not re.fullmatch(r'[a-f0-9]{32}', run_id):
        raise ValueError('Invalid check run ID')
    directory = Path(root) / 'tasks' / task_id / 'check-output'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / (run_id + '.log')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data[:RAW_LIMIT])
    for old in sorted(directory.glob('*.log'), key=lambda p: p.stat().st_mtime_ns, reverse=True)[KEEP_RUNS:]:
        old.unlink()
    return {'bytes': min(len(data), RAW_LIMIT), 'truncated': truncated or len(data)>RAW_LIMIT,
            'retention': 'Latest 8 runs; at most 2 MB per run'}


def raw(store, task_id, run_id):
    task = store.get(task_id)  # Resolve known task before constructing any path.
    if not re.fullmatch(r'[a-f0-9]{32}', run_id) or not any(c.get('run_id')==run_id and c.get('raw_output') for c in task.get('checks',[])):
        raise ValueError('Unknown retained check run')
    path = store.root / 'tasks' / task_id / 'check-output' / (run_id+'.log')
    try:
        with path.open('rb') as stream:
            return stream.read(RAW_LIMIT)
    except FileNotFoundError:
        raise ValueError('Raw output expired; only the latest 8 runs are retained') from None


def read(store, task_id, run_id, offset=0):
    if type(offset) is not int or offset<0 or offset>RAW_LIMIT:
        raise ValueError('Offset must be a byte position within retained output')
    data=raw(store,task_id,run_id)
    # Byte pagination: UTF-8 boundaries may display replacement characters; the
    # operator download preserves original bytes exactly.
    chunk=data[offset:offset+8000]
    return {'run_id':run_id,'offset':offset,'next_offset':offset+len(chunk),
            'has_more':offset+len(chunk)<len(data),'output':chunk.decode('utf-8','replace'),
            'retained_bytes':len(data),'note':'Unfiltered retained output; see check result for truncation and authoritative status.'}


def summarize(text):
    """Drop only unmistakable passing unittest rows; retain every other line."""
    clean=ANSI.sub('',text)
    if not RUN_SUMMARY.search(clean):
        return text,0
    lines=clean.splitlines(keepends=True)
    omitted=sum(bool(PASS_LINE.fullmatch(line.rstrip('\r\n'))) for line in lines)
    if not omitted:
        return text,0
    result=''.join(line for line in lines if not PASS_LINE.fullmatch(line.rstrip('\r\n')))
    result=f'[{omitted} passing unittest rows omitted; use read_check_output with this run_id for original bytes.]\n'+result
    return (result,omitted) if len(result.encode())<len(text.encode()) else (text,0)


def messages(task, original, config):
    # Direct local only: unknown gateway compression cannot silently stack with us.
    enabled=task.get('check_output_filter')=='unittest' and not task.get('route') and not config.get('gateway') and config.get('base_url','').startswith(('http://127.0.0.1:11434/','http://localhost:11434/'))
    if not enabled:
        return original,{'layer':'none','omitted_rows':0}
    checks={c.get('run_id'):c for c in task.get('checks',[])[-KEEP_RUNS:] if c.get('raw_output') and not c.get('truncated')}
    omitted=0
    def visit(value):
        nonlocal omitted
        if isinstance(value,list):return [visit(v) for v in value]
        if not isinstance(value,dict):return value
        known=checks.get(value.get('run_id')) if isinstance(value.get('run_id'),str) else None
        if known and value.get('output')==known['output'] and value.get('command')==known['command'] and 'exit_code' in value:
            output,count=summarize(known['output'])
            if count:
                omitted+=count
                return {**value,'output':output,'output_representation':'cheapos-unittest-summary-v1'}
        return {k:visit(v) for k,v in value.items()}
    result=copy.deepcopy(original)
    for message in result:
        if message.get('role') not in {'tool','user'} or not isinstance(message.get('content'),str):continue
        if message['content'] in task.get('requests',[]):continue
        try:value=json.loads(message['content'])
        except (ValueError,TypeError):continue
        transformed=visit(value)
        if transformed!=value:message['content']=json.dumps(transformed)
    return result,{'layer':'cheapos-unittest-v1' if omitted else 'none','omitted_rows':omitted}
