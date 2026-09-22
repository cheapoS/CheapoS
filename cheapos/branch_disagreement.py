"""Additive evidence for new Unattended disagreements; never execution authority."""
from .instructions.runtime import text as instruction
import copy
import hashlib
import json
import re
from .development import enabled as developing

REVIEW_INSTRUCTION = instruction('reviewer.defects')
REPAIR_INSTRUCTION = instruction('recovery.disagreement')


def invalid_review(message):
    error=ValueError(message)
    error.code='invalid_response_json';error.stage='reviewing'
    error.safe_diagnostic={'kind':'safe_message','message':'Review remains unfinished: '+message}
    return error


def decision(result, takeover=False):
    value = result.get('decision')
    allowed = {'APPROVE', 'REQUEST_CHANGES', 'REQUEST_TESTS'} | ({'TAKE_OVER'} if takeover else set())
    if not isinstance(value, str) or value.strip().upper() not in allowed:
        raise invalid_review('Return an explicit valid review decision; feedback cannot imply approval.')
    value = value.strip().upper()
    if value == 'APPROVE' and result.get('defects') not in (None, []):
        raise invalid_review('APPROVE cannot contain unresolved blocking defects. If no blocking defect remains, '
            'return defects: [] and put confirmations in criteria_outcomes evidence or feedback. '
            'If a blocking defect remains, return REQUEST_CHANGES with concrete defects.')
    return value

def schema(criteria=None):
    fields = {name: {'type': 'string'} for name in
              ('criterion', 'location', 'expected', 'observed', 'support', 'reproduction')}
    if criteria:
        fields['criterion']['enum'] = list(criteria)
        fields['criterion']['description'] = f"Must be one of exact criteria: {json.dumps(list(criteria))}"
    fields['finding_id'] = {'type':'string','description':'Optional existing finding ID from the repair brief; omit for a new claim.'}
    fields['kind'] = {'type': 'string', 'enum': ['static', 'executable']}
    return {'type': 'array', 'minItems': 0, 'maxItems': 8,
        'description': 'Blocking defects only. For APPROVE return []; REQUEST_CHANGES requires 1–8 supported defects. Positive confirmations belong in criterion evidence or feedback; optional advice belongs in suggestions.', 'items': {
        'type': 'object', 'properties': fields, 'required': [k for k in fields if k!='finding_id'], 'additionalProperties': False}}


def validate(result, criteria):
    """Validate actionable structure, not the truth of a model's claim."""
    defects = result.get('defects')
    if not isinstance(defects, list) or not 1 <= len(defects) <= 8:
        raise invalid_review('REQUEST_CHANGES needs 1–8 supported defects; feedback alone cannot authorize repair.')
    required = set(schema()['items']['required'])
    cleaned_defects = []
    for defect in defects:
        if not isinstance(defect, dict):
            raise invalid_review('Each defect needs to be a dictionary.')
        defect = dict(defect)
        for alias, canonical in (('expected_behavior','expected'),('observed_behavior','observed'),('code_location','location')):
            if alias not in defect: continue
            value = defect.pop(alias)
            if alias == 'code_location' and isinstance(value, dict):
                if set(value) != {'path','line_start'} or not isinstance(value['path'],str) or type(value['line_start']) is not int or value['line_start'] < 1:
                    raise invalid_review('Legacy code_location requires an explicit path and positive line_start.')
                value = value['path']+':'+str(value['line_start'])
            if canonical in defect and defect[canonical] != value:
                raise ValueError('Conflicting finding aliases for '+canonical)
            defect[canonical] = value
        defect.setdefault('reproduction','')
        if not isinstance(defect['reproduction'],str):
            raise invalid_review('Defect reproduction must be a string.')
        if 'kind' not in defect:
            if not defect['reproduction'].strip():
                raise invalid_review('Specify static or executable kind; missing reproduction cannot imply static.')
            defect['kind'] = 'executable'
        if not required.issubset(set(defect)):
            raise invalid_review('Each defect needs criterion, location, expected, observed, kind, support and reproduction.')
        if not isinstance(defect['criterion'],str) or defect['criterion'] not in criteria:
            raise ValueError('Defect criterion must match a supplied acceptance criterion: ' + repr(criteria))
        if not isinstance(defect['kind'],str) or defect['kind'] not in {'static', 'executable'}:
            raise invalid_review('Defect kind must be static or executable.')
        for field in required - {'kind'}:
            value = defect[field]
            if not isinstance(value, str) or len(value) > 2000 or (field != 'reproduction' and not value.strip()):
                raise ValueError('Defect ' + field + ' must contain bounded concrete evidence.')
        location=defect['location']
        path, sep, line=location.rpartition(':')
        if not sep or not re.fullmatch(r'[1-9][0-9]*(?:-[1-9][0-9]*)?',line) or not path or path.startswith(('/', '\\')) or '..' in path.replace('\\','/').split('/'):
            raise invalid_review('Defect location requires a relative file and positive line/range.')
        if '-' in line and int(line.split('-')[1]) < int(line.split('-')[0]):
            raise invalid_review('Defect location range is reversed.')
        if defect['kind'] == 'executable' and not defect['reproduction'].strip():
            raise invalid_review('Executable defects need a concrete example/reproduction; it is not command consent.')
        cleaned={k:defect[k] for k in required}
        if 'finding_id' in defect:
            if not isinstance(defect['finding_id'],str) or not re.fullmatch(r'[a-f0-9]{24}',defect['finding_id']):raise invalid_review('Invalid finding reference.')
            cleaned['finding_id']=defect['finding_id']
        cleaned_defects.append(cleaned)
    return cleaned_defects


def ensure_available(task, key, *, baseline=0):
    from .engine import ProgressPause
    saved = task['branch_run'].get('review_disagreements', {}).get(key, {})
    if not developing(task) and saved.get('unsupported_attempts', 0) - baseline >= 3:
        raise ProgressPause('Unsupported review disagreement persisted three times. Saved evidence is retained; Resume does not renew these attempts. Provide new evidence or revise the task explicitly.')


def unsupported(engine, task, key, result, error):
    saved = task['branch_run'].setdefault('review_disagreements', {}).setdefault(key, {})
    saved['unsupported_attempts'] = saved.get('unsupported_attempts', 0) + 1
    saved['last_unsupported'] = copy.deepcopy(result)
    feedback = {'error': str(error), 'supported': False, 'attempt': saved['unsupported_attempts'],
                **getattr(error, 'correction', {})}
    engine.event(task, 'review_feedback', 'Review disagreement needs concrete evidence', feedback)
    engine.store.save(task)
    return feedback


def repair(result, candidate_id, checks):
    result=copy.deepcopy(result)
    if result.get('defects'):
        result['defects']=validate(result,[d.get('criterion') for d in result['defects']])
    return {**result, 'candidate_id': candidate_id,
            'checks': copy.deepcopy(checks), 'repair_instruction': REPAIR_INSTRUCTION}


def attach(task, item, result):
    """Persist a disputed candidate and probe baseline before any worker edit."""
    if result.get('defects') and not result.get('manifest_id'):
        from .engine import ProgressPause
        key = hashlib.sha256(json.dumps(result['defects'], sort_keys=True).encode()).hexdigest()
        claims = task['branch_run'].setdefault('repair_claims', {})
        if not developing(task) and claims.get(key, 0) >= 3:
            raise ProgressPause('The same review disagreement has requested repair three times. Retain the evidence and resolve the disagreement explicitly; no further identical repair was started.')
        claims[key] = claims.get(key, 0) + 1
    from .review_disputes import register
    result=copy.deepcopy(result)
    register(task,item,result)
    item['review_repair'] = result
    item['review_repair']['check_start'] = len(task.get('checks', []))


class SavedRepairError(ValueError):
    """Invalid controller-owned evidence, not a failed model response."""
    code='controller_error'

    def __init__(self, message):
        super().__init__(message)
        self.safe_diagnostic={'kind':'safe_message','message':message}


def allowed_criteria(task,item):
    repair=item.get('review_repair',{})
    if not repair.get('defects') and not repair.get('requirement_refs'):
        return item.get('acceptance_criteria',[])
    run=task.get('branch_run',{});refs=repair.get('requirement_refs')
    if refs:
        from .repair_scope import review_criteria
        criteria=review_criteria(run,refs,repair.get('defects',[]))
    else:
        plan=run.get('authorization',{}).get('contract',{}).get('plan',run.get('plan'))
        original=next((i for i in plan.get('items',[]) if i['id']==item.get('id')),None) if plan else item
        if not original:raise ValueError('Saved repair has no authorized requirement mapping.')
        criteria=original.get('acceptance_criteria',[])
    return criteria


def pending(task,item):
    repair=item.get('review_repair',{})
    if not repair.get('defects'):return repair
    try:
        repair['defects']=validate(repair,allowed_criteria(task,item))
    except (ValueError, KeyError, TypeError, IndexError) as error:
        raise SavedRepairError('Saved review findings could not be validated: '+str(error)) from error
    return repair


def before_write(task, path):
    """Executable claims require an actual check failure before implementation edits.

    Test-file staging is permitted to create the regression. This does not prove
    its assertion describes the claim; independent review still judges that.
    """
    from .verification import evidence_identity
    from .check_output import complete_output
    run = task.get('branch_run', {})
    item = next((i for i in run.get('items', []) if i['id'] == run.get('current_item_id')), {})
    repair = item.get('review_repair', {})
    if repair.get('defects'):
        try:
            pending(task,item)
        except ValueError as error:
            raise SavedRepairError('Saved review findings need validation before editing: '+str(error)) from error
    if not any(d.get('kind') == 'executable' for d in repair.get('defects', [])) or repair.get('probe_observed'):
        return
    for record in task.get('checks', [])[repair.get('check_start', len(task.get('checks', []))) :]:
        if (record.get('passed') is False and record.get('outcome') == 'test_failure'
                and not record.get('reason') and complete_output(record)
                and isinstance(record.get('exit_code'), int) and record['exit_code'] != 0
                and record.get('input_identity')
                and record['input_identity'] == evidence_identity({**task, 'check_command': record['command'], 'check_directory': record.get('directory', '.')})):
            repair['probe_observed'] = {'run_id': record.get('run_id'), 'input_identity': record['input_identity'],
                                        'command': copy.deepcopy(record['command'])}
            return
    if test_path(path):
        return
    from .workspace import FileEditConstraint
    raise FileEditConstraint('repair_evidence_required', f"Demonstrate the executable defect with a failing check before editing '{path}'. Add a narrow regression to a test file covered by a planned check, then run that check. Preserve existing assertions. If the claim is disproved, submit concrete counterevidence at checkpoint instead of changing correct behavior.")


def test_path(path):
    from pathlib import PurePosixPath
    name = PurePosixPath(str(path).replace('\\', '/'))
    if ('..' not in name.parts and not name.is_absolute() and
            (any(part in {'test', 'tests', '__tests__'} for part in name.parts[:-1])
             or name.name.startswith('test_') or '.test.' in name.name or '.spec.' in name.name
             or name.stem.endswith('_test'))):
        return True
    return False


def reproduction_context(task, workspace):
    """Point at the current check's tests; never execute reviewer snippets."""
    from .branch_evidence import commands
    run = task.get('branch_run') or {}
    item = next((i for i in run.get('items', []) if i['id'] == run.get('current_item_id')), {})
    repair = pending(task, item)
    checks = commands(item.get('required_checks', []))
    paths = []
    for argv in checks:
        for arg in argv[1:]:
            candidates = [arg] if arg.endswith('.py') else []
            if 'unittest' in argv and re.fullmatch(r'[\w]+(?:\.[\w]+)*', arg):
                parts = arg.split('.')
                candidates += ['/'.join(parts[:n])+'.py' for n in range(len(parts), 0, -1)]
            for path in candidates:
                try:
                    if test_path(path) and workspace.path(path).is_file() and path not in paths:
                        paths.append(path)
                        break
                except (ValueError, OSError):
                    continue
    result = {'candidate_id': repair.get('candidate_id'), 'planned_checks': checks,
              'test_files': paths, 'findings': [{k:d.get(k) for k in
                  ('finding_id','location','expected','observed','kind','support','reproduction')} for d in repair.get('defects', [])]}
    if paths:
        try:
            result['current_test_file'] = workspace.read_file(paths[0], 1, 80)
        except (ValueError, OSError, UnicodeError) as error:
            result['test_file_read_error'] = str(error)[:500]
    return result
