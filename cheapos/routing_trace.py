"""Bounded, allowlisted routing evidence; never stores prompts or endpoint labels."""
import math
import re

LIMIT = 32
REASONS = {'eligible','access_excluded','local_excluded','capability_missing','context_insufficient',
           'fit_unknown','prior_worker','failed_model','cooldown','cached_probe','shared_probe',
           'probe_required','selected','connection_unavailable','caller_error'}
CATEGORIES = {'credential_access','malformed_request','capability_mismatch','unavailable_route',
              'rate_limit_quota','transient_provider','invalid_response','cancelled','unknown'}


def model_label(value):
    # Model metadata is untrusted. Reject URLs, whitespace, queries and credentials.
    if not isinstance(value,str) or len(value)>160 or not re.fullmatch(r'[A-Za-z0-9_.:/+@-]+',value):return 'unknown'
    if '://' in value or '@' in value:return 'unknown'
    return value


def begin(task, role, requested_route=None):
    traces=task.setdefault('routing_traces',[])
    sequence=task.get('routing_trace_sequence',0)+1;task['routing_trace_sequence']=sequence
    trace={'id':str(sequence),'role':role if role in ('worker','reviewer','coordinator') else 'unknown',
           'requested_route':model_label(requested_route),'candidates':[],'attempts':[],
           'selected_model':None,'gateway_attempts':'unavailable'}
    run_id=task.get('metric_run_id')
    trace['run_id']=run_id if isinstance(run_id,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,80}',run_id) else None
    traces.append(trace)
    if len(traces)>LIMIT:del traces[:-LIMIT];task['routing_traces_truncated']=True
    return trace


def candidate(trace, model, reason):
    row={'model':model_label(model),'reason':reason if reason in REASONS else 'unknown'}
    if len(trace['candidates'])<64:trace['candidates'].append(row)
    else:
        trace['candidates_truncated']=True
        # Retain actual selection actions even when a large discovery catalog
        # has filled the bounded list with excluded entries.
        actions={'cached_probe','shared_probe','probe_required','selected'}
        if reason in actions:
            discard=next((i for i,c in enumerate(trace['candidates']) if c['reason'] not in actions),0)
            trace['candidates'].pop(discard);trace['candidates'].append(row)


def selected(trace, model):
    trace['selected_model']=model_label(model)


def request(task, metric):
    if not metric.get('dispatched'):return
    role=metric.get('role');request_id=metric.get('id')
    if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',request_id):return
    traces=task.setdefault('routing_traces',[])
    trace=next((t for t in reversed(traces) if t['role']==role and t.get('run_id')==task.get('metric_run_id')),None)
    if trace is None:
        trace=begin(task,role,metric.get('model'))
        if metric.get('purpose')!='probe':selected(trace,metric.get('model'))
    row={'request_id':request_id,'model':model_label(metric.get('model')),
         'purpose':metric.get('purpose') if metric.get('purpose') in ('probe','branch_planning','branch_final','work','review') else 'work',
         'status':metric.get('status') if metric.get('status') in ('pending','responded','failed','cancelled') else 'unknown',
         'served_model':model_label(metric.get('served_model')) if metric.get('served_model') else None,
         'identity_provenance':'response_model' if metric.get('identity_provenance')=='response_model' else 'unknown',
         'failure_category':metric.get('failure_category') if metric.get('failure_category') in CATEGORIES else None}
    seconds=metric.get('seconds')
    if isinstance(seconds,(int,float)) and not isinstance(seconds,bool) and math.isfinite(seconds) and seconds>=0:row['seconds']=seconds
    index=next((i for i,a in enumerate(trace['attempts']) if a['request_id']==request_id),None)
    if index is not None:trace['attempts'][index]=row
    else:
        trace['attempts'].append(row)
        if len(trace['attempts'])>64:del trace['attempts'][:-64];trace['attempts_truncated']=True


def context_fit(task, model):
    """Reject only proven insufficiency; unknown estimates never become fact."""
    if model.get('tool_calling') is False:return 'capability_missing'
    limit=model.get('context_length')
    required=task.get('routing_required_context_tokens')
    if (isinstance(limit,(int,float)) and not isinstance(limit,bool) and math.isfinite(limit) and limit>0
        and isinstance(required,(int,float)) and not isinstance(required,bool) and math.isfinite(required) and required>limit):
        return 'context_insufficient'
    return 'fit_unknown'
