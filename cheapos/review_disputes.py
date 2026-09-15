"""Conservative durable dispute tracking, without semantic model calls."""
import copy
import hashlib
import json
import re
from .development import enabled as developing


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
def normalized(value):return ' '.join(re.findall(r'\w+',value.lower()))
def location(finding):return finding['location'].rsplit(':',1)[0]


def register(task, item, repair):
    run=task['branch_run'];ledger=run.setdefault('dispute_ledger',{'version':1,'findings':{}})
    records=ledger['findings'];ids=[]
    for finding in repair.get('defects',[]):
        criterion=finding['criterion']
        mapped=[r['id'] for r in repair.get('requirement_refs',[]) if r['criterion']==criterion]
        prior=records.get(finding.get('finding_id'),{})
        if mapped:
            previous=prior.get('structural',{}).get('criterion')
            if previous in mapped:criterion=previous
            elif len(mapped)==1:criterion=mapped[0]
            else:raise ValueError('Use an existing finding_id to distinguish identical original requirement text.')
        elif criterion in item.get('acceptance_criteria',[]):criterion=f"{item['id']}:{item['acceptance_criteria'].index(criterion)+1}"
        structural={'criterion':criterion,'path':location(finding)}
        signature=digest({**structural,'expected':normalized(finding['expected']),'observed':normalized(finding['observed']),'reproduction':normalized(finding['reproduction']),'kind':finding['kind']})[:24]
        supplied=finding.get('finding_id')
        record=records.get(supplied) if supplied else records.get(signature)
        if supplied and (not record or record['structural']!=structural):raise ValueError('Finding reference does not match a known requirement/location.')
        if record and record['status']=='independently_resolved':
            signature=digest([signature,repair['candidate_id']])[:24];record=records.get(signature)
        key=record['id'] if record else signature
        if record is None:
            if len(records)>=96:
                from .branch_pause import PauseError
                raise PauseError('repeated_review_dispute')
            similar=[r['id'] for r in records.values() if r['structural']==structural and r['status']!='independently_resolved']
            record={'id':key,'structural':structural,'status':'requested','attempts':0,'history':[],'possible_repeats':similar[-8:]}
            records[key]=record
        if not developing(task) and record['attempts']>=3:
            from .branch_pause import PauseError
            raise PauseError('repeated_review_dispute')
        record['attempts']+=1;record['status']='requested'
        record['history'].append({'candidate_id':repair['candidate_id'],'finding':copy.deepcopy(finding),'item_id':item.get('id')})
        finding['finding_id']=key;ids.append(key)
    repair['finding_ids']=ids
    repair['prior_counterevidence']=[copy.deepcopy(records[key]['worker_counterevidence']) for key in ids if records[key].get('worker_counterevidence')]


def dispositions(task, item, args, candidate):
    repair=item.get('review_repair')
    if not repair or not repair.get('defects'):return []
    supplied=args.get('repair_dispositions')
    if not isinstance(supplied,list) or len(supplied)!=len(repair['defects']):raise ValueError('Provide one repair_disposition for every finding with candidate_id and concrete evidence.')
    expected={f['finding_id'] for f in repair['defects']};seen=set();clean=[]
    for value in supplied:
        if not isinstance(value,dict) or value.get('finding_id') not in expected or value['finding_id'] in seen or value.get('candidate_id')!=repair['candidate_id']:
            raise ValueError('Disposition must match each finding and the current candidate exactly once.')
        if value.get('disposition') not in {'reproduced_and_corrected','disproved','unresolved'}:raise ValueError('Invalid repair disposition.')
        for field in ('evidence','broader_edit_reason'):
            if field not in value and field=='broader_edit_reason':continue
            if not isinstance(value.get(field),str) or len(value[field])>2000 or (field=='evidence' and not value[field].strip()):raise ValueError('Supply bounded concrete repair evidence.')
        seen.add(value['finding_id']);clean.append({k:value[k] for k in ('finding_id','candidate_id','disposition','evidence','broader_edit_reason') if k in value})
    affected={location(f) for f in repair['defects']}
    def sections(patch):
        result={}
        for section in patch.split('diff --git ')[1:]:
            header=section.split('\n',1)[0]
            if ' b/' in header:result[header.rsplit(' b/',1)[1]]=section
        return result
    before=sections(repair.get('source_patch',''));after=sections(task.get('patch',''))
    changed=[path for path in before.keys()|after.keys() if before.get(path)!=after.get(path)]
    broad=[path for path in changed if path not in affected and not any(t in path for t in ('test','spec'))]
    if broad and not any(v.get('broader_edit_reason','').strip() for v in clean):raise ValueError('Explain why the repair changes files outside the finding locations in broader_edit_reason.')
    for value in clean:value['reviewed_candidate_id']=candidate
    repair['dispositions']=copy.deepcopy(clean)
    records=task['branch_run'].get('dispute_ledger',{}).get('findings',{})
    for value in clean:
        record=records.get(value['finding_id'])
        if record:record['worker_counterevidence']=copy.deepcopy(value) # allegation, not independent resolution
    return clean


def resolved(task,item,candidate):
    records=task['branch_run'].get('dispute_ledger',{}).get('findings',{})
    for key in item.get('review_repair',{}).get('finding_ids',[]):
        if key in records:records[key].update(status='independently_resolved',resolved_candidate=candidate)


def brief(repair):
    return {k:copy.deepcopy(repair[k]) for k in ('candidate_id','requirement_refs','defects','checks','repair_instruction','dispositions','finding_ids','prior_counterevidence') if k in repair}
