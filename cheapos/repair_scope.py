"""Original requirement references for bounded controller amendments."""
import copy


def requirements(run):
    original=run['authorization']['contract']['plan']
    return [{'id':f"{item['id']}:{i+1}",'item_id':item['id'],'criterion':criterion}
            for item in original['items'] for i,criterion in enumerate(item['acceptance_criteria'])]


def select(run, references=None):
    available=requirements(run);by_id={r['id']:r for r in available}
    if references is None:
        if len(available)>12:raise ValueError('Select 1–12 original requirement IDs in the revision preview before starting repair.')
        references=list(by_id)
    if not isinstance(references,list) or not 1<=len(references)<=12 or any(not isinstance(r,str) for r in references) or len(set(references))!=len(references):
        raise ValueError('Select 1–12 distinct original requirement IDs.')
    if any(r not in by_id for r in references):raise ValueError('Unknown or stale original requirement reference.')
    return [copy.deepcopy(by_id[r]) for r in references]


def findings_refs(run, findings):
    refs=[]
    original={r['id'] for r in requirements(run)}
    for finding in findings:
        ref=finding['criterion']
        if ref not in original:
            item_id,_,position=ref.rpartition(':')
            amendment=next((a for a in run.get('amendments',[]) if a['item']['id']==item_id),None)
            if not amendment or not position.isdigit():raise ValueError('Finding has no original requirement mapping.')
            text=amendment['item']['acceptance_criteria'][int(position)-1] if 0<int(position)<=len(amendment['item']['acceptance_criteria']) else None
            mapped=[r['id'] for r in amendment.get('requirement_refs',[]) if r['criterion']==text]
            if not mapped:raise ValueError('Legacy repair needs an inspected original requirement selection.')
            refs.extend(mapped)
        else:refs.append(ref)
    return list(dict.fromkeys(refs))
