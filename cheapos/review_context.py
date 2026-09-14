"""Bounded immutable final-review context; never reads the live working tree."""
import hashlib
from pathlib import PurePosixPath
from . import branch_workspace as work
from .workspace import allowed_name


def chunks(content, limit):
    """Prefer line/file/hunk boundaries, preserving every character in order."""
    if not content:return ['']
    output=[]
    while content:
        stop=min(limit,len(content))
        if stop<len(content):
            preferred=max(content.rfind('\ndiff --git ',0,stop),content.rfind('\n@@ ',0,stop))
            line=content.rfind('\n',0,stop)
            if preferred>limit//3:stop=preferred+1
            elif line>0:stop=line+1
        output.append(content[:stop]);content=content[stop:]
    return output


def read(run, manifest, args):
    if set(args)-{'manifest_id','path','start_line','end_line'} or args.get('manifest_id')!=manifest['id']:
        raise ValueError('Context requires this exact manifest identity.')
    mapping=run['workspace_mapping'];source=mapping['source'];tip=manifest['feature_tip']
    if run.get('expected_feature_tip')!=tip or work._tip(source,manifest['feature_ref'])!=tip or work.source_git(source,'rev-parse',tip+'^{tree}')!=manifest['feature_tree']:
        raise ValueError('Final candidate changed; context is stale.')
    path=args.get('path');start=args.get('start_line',1)
    if type(start) is not int:raise ValueError('Context start_line must be an integer.')
    end=args.get('end_line',start+79)
    if not isinstance(path,str) or not path or '\\' in path or '\x00' in path or PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts or not allowed_name(path):
        raise ValueError('Context path is outside permitted project files.')
    if type(start) is not int or type(end) is not int or not 1<=start<=end or end-start>=200:
        raise ValueError('Request a positive range of at most 200 lines.')
    entry=work.source_git(source,'ls-tree','-z',tip,'--',path,binary=True)
    provenance={'manifest_id':manifest['id'],'candidate':tip,'tree':manifest['feature_tree'],'path':path}
    if not entry:return {**provenance,'available':False,'reason':'File absent from this candidate.'}
    entries=[e for e in entry.split(b'\0') if e]
    if len(entries)!=1 or entries[0].partition(b'\t')[2].decode()!=path:raise ValueError('Context requires one exact literal file path.')
    mode,kind,rest=entries[0].partition(b'\t')[0].split(b' ',2)
    if mode not in (b'100644',b'100755') or kind!=b'blob':raise ValueError('Only regular candidate files may be inspected.')
    oid=rest.decode();size=int(work.source_git(source,'cat-file','-s',oid))
    if size>2_000_000:return {**provenance,'available':False,'reason':'Candidate file exceeds bounded context size.'}
    raw=work.source_git(source,'cat-file','blob',oid,binary=True)
    try:text=raw.decode('utf-8')
    except UnicodeError:return {**provenance,'available':False,'reason':'Candidate file is not UTF-8 text.'}
    lines=text.splitlines();selected=lines[start-1:end];numbered=[];length=0
    for n,line in enumerate(selected,start):
        value=f'{n}: {line}'
        if length+len(value)>12000:break
        numbered.append(value);length+=len(value)+1
    return {**provenance,'available':True,'blob':oid,'digest':hashlib.sha256(raw).hexdigest(),
            'start_line':start,'end_line':start+len(numbered)-1,'total_lines':len(lines),
            'range_complete':len(numbered)==len(selected),'complete_file':start==1 and len(numbered)==len(lines),
            'truncated':len(numbered)<len(selected) or start>1 or end<len(lines),'content':'\n'.join(numbered)}
