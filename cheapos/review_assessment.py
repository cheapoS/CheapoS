"""Candidate-bound review citations. Provenance is verified; model judgment is not.

Only the controller registers delivered evidence. A check passing or a previous
approval is never implementation evidence on its own. No new execution authority.
"""
import copy
import hashlib
import json
import re

VERSION = 1
INSTRUCTION = '''Approval needs review_assessment, not just passing checks. For every criterion explain how the requested behavior follows from actual code/document evidence. Cite exact nonempty excerpts using source IDs from review_evidence or evidence_id returned by a read tool. Review regressions and verification separately: examine changed/removed handlers, callers, styles, imports, tests and assertions as relevant. Examine whether assertions would fail if the requested behavior were missing, and whether changed tests weaken expectations, remove coverage, or replace behavior with permissive mocks. Explain what the checks establish and what they miss; a green command or the worker's description alone cannot establish correctness. For UI changes inspect related styles, icons and interactions; source inspection is not a rendered visual check. List remaining verification limitations honestly. Missing evidence means use the read tools or request focused tests within existing authority, not guess, approve, or invent a defect. Do not manufacture findings on correct work. Earlier approvals are claims, not source evidence. The original request is context for detecting omissions; the approved scope and latest explicit amendments remain authoritative.'''


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def enabled(task):
    return task.get('review_contract_version') == VERSION


def original_request(task):
    from .context_evidence import retain
    value = {'request': task.get('prompt', ''), 'directions': task.get('requests', []),
             'captured_inputs': task.get('branch_run', {}).get('inputs', {})}
    text = json.dumps(value, ensure_ascii=False)
    if len(text) <= 12000:
        return value
    return {'reference': retain(task, value, 'original_review_request'),
            'request': task.get('prompt', '')[:4000],
            'retrieve': 'Read the captured request and directions with read_context_evidence; this excerpt is incomplete.'}


def add(state, source, kind, content, **metadata):
    if not isinstance(content, str) or not content.strip():
        return None
    state['sources'][source] = {'kind': kind, 'content': content, 'digest': digest(content), **metadata}
    return source


def prepare(scope, packet, criteria, *, partial=False):
    state = {'version': VERSION, 'scope': scope, 'criteria': list(criteria) or ['packet'],
             'partial': partial, 'sources': {}}
    add(state, 'diff', 'code', packet.get('diff'), format='diff')
    checks = packet.get('checks') or packet.get('review_context', {}).get('final_checks')
    if checks:
        add(state, 'checks', 'check', json.dumps(checks, ensure_ascii=False, sort_keys=True))
    chunk = packet.get('chunk')
    if isinstance(chunk, dict):
        add(state, 'packet', 'code' if chunk.get('kind') == 'diff' else 'packet', chunk.get('content'),
            format='diff' if chunk.get('kind') == 'diff' else 'text')
    if 'page_index' in packet:
        add(state, 'packet', 'packet', packet.get('content'))
    # Synthesis receives exact excerpts from approved chunks, not just verdicts.
    # These are controller-validated citations of this manifest's content.
    for index, row in enumerate(packet.get('coverage', [])):
        for source, value in row.get('review', {}).get('_review_evidence', {}).get('excerpts', {}).items():
            add(state, f'chunk:{index + 1}:{source}', value['kind'], value['content'])
    if partial and not state['sources']:
        add(state, 'packet', 'packet', json.dumps(packet, ensure_ascii=False))
    return state


def display(state):
    sources = []
    for source, value in state['sources'].items():
        row = {'id': source, 'kind': value['kind'], 'digest': value['digest']}
        row.update({key: value[key] for key in ('path', 'format') if key in value})
        if source.startswith('chunk:'):
            row['content'] = value['content']  # The synthesizer must see the cited code.
        sources.append(row)
    return {'version': VERSION, 'scope': state['scope'], 'criteria': state['criteria'], 'sources': sources,
            'instruction': 'Use an exact source id below (not a file path). Use read_review_evidence(source, offset, search) to retrieve or search these sources when a citation is unclear. Quote a short literal excerpt from that delivered source. Display line numbers and diff gutters may be omitted; code indentation and wording must stay exact. Reuse delivered evidence; read only missing context. Checks alone do not prove requested behavior.'}


def read(state, source=None, offset=0, search=None):
    """Page only this candidate's delivered evidence, including after handoff."""
    if source is None:
        return display(state)
    if not isinstance(source, str) or source not in state['sources']:
        return {'error': 'Unknown current review source. Use one of the listed IDs.', **display(state)}
    value = state['sources'][source]
    content = value['content']
    if type(offset) is not int or not 0 <= offset <= len(content):
        raise ValueError('Offset must be a character position within this review source.')
    if search is not None:
        if not isinstance(search, str) or not 1 <= len(search) <= 500:
            raise ValueError('Search must be 1–500 literal characters.')
        found = content.find(search, offset)
        if found < 0:
            return {'evidence_id': source, 'found': False, 'next_offset': offset}
        offset = max(offset, found - 500)
    page = content[offset:offset + 8000]
    return {'evidence_id': source, 'scope': state['scope'], 'kind': value['kind'],
            'digest': value['digest'], 'offset': offset, 'next_offset': offset + len(page),
            'has_more': offset + len(page) < len(content), 'content': page,
            'instruction': 'Cite this evidence_id and a literal quote from its content. This read does not approve anything.'}


def packet_for_model(packet):
    """Keep source excerpts in the catalog once; full receipts remain saved."""
    result = copy.deepcopy(packet)
    for row in result.get('coverage', []):
        prior = row.get('review', {})
        if prior.get('_review_evidence', {}).get('version') != VERSION:
            continue
        prior['feedback'] = visible_feedback(prior)
        prior.pop('_review_evidence', None)
        prior.pop('review_assessment', None)
    return result


def schema(state):
    citation = {'type': 'object', 'properties': {
        'source': {'type': 'string', 'minLength': 1, 'description': 'Exact review_evidence source id or read tool evidence_id; not a file path.'},
        'quote': {'type': 'string', 'minLength': 1, 'description': 'Short literal excerpt from this source. Preserve code whitespace; display line numbers/diff gutters are optional.'}},
                'required': ['source', 'quote'], 'additionalProperties': False}
    claim = {'type': 'object', 'properties': {'reason': {'type': 'string', 'minLength': 1},
             'citations': {'type': 'array', 'minItems': 1, 'items': citation}}, 'required': ['reason', 'citations'], 'additionalProperties': False}
    return {'type': 'object', 'description': 'Required for APPROVE. Supply all four fields; each claim needs a nonempty reason and citations. Use [] for no verification limitations.', 'properties': {
        'criteria': {'type': 'object', 'properties': {key: copy.deepcopy(claim) for key in state['criteria']},
                     'required': state['criteria'], 'additionalProperties': False},
        'regressions': copy.deepcopy(claim), 'verification': copy.deepcopy(claim),
        'limitations': {'type': 'array', 'items': {'type': 'string'}}},
        'required': ['criteria', 'regressions', 'verification', 'limitations'], 'additionalProperties': False}


def tools_with_contract(tools, state, name='review_decision'):
    tools = copy.deepcopy(tools)
    decision = next(t for t in tools if t['function']['name'] == name)['function']['parameters']
    # Only APPROVE requires this field; rejection must remain available.
    decision['properties']['review_assessment'] = schema(state)
    # Keep saved receipt compatibility without asking for the same assessment twice.
    decision['properties'].pop('criteria_outcomes', None)
    decision['required'] = [key for key in decision.get('required', []) if key != 'criteria_outcomes']
    tools.append({'type': 'function', 'function': {
        'name': 'read_review_evidence',
        'description': 'Read/search the current review evidence by source ID, including checks, diffs and prior candidate reads. Omit source to list IDs. Returns 8000 characters with next_offset; no files are changed and no checks are executed.',
        'parameters': {'type': 'object', 'properties': {
            'source': {'type': 'string'}, 'offset': {'type': 'integer', 'minimum': 0},
            'search': {'type': 'string', 'minLength': 1, 'maxLength': 500}},
            'required': [], 'additionalProperties': False}}})
    return tools


def observation(state, name, args, result):
    if name == 'get_diff' and isinstance(result, str):
        result = {'content': result}
    if not isinstance(result, dict) or result.get('error') or result.get('available') is False:
        return result
    kind = 'code' if name in {'read_file', 'read_final_context', 'get_diff'} else 'check' if name == 'read_check_output' else None
    content = result.get('content') or (result.get('output') if name == 'read_check_output' else None)
    if name == 'inspect_image' and result.get('status') == 'success':
        kind = 'code' if result.get('format') == 'svg' else 'image'
        content = result.get('analysis')
    if not kind or not content:
        return result
    source = 'read:' + digest({'scope': state['scope'], 'tool': name, 'arguments': args, 'content': content})[:20]
    metadata = {}
    if name in {'read_file', 'read_final_context'}:
        metadata = {'format': 'numbered', 'path': result.get('path') or args.get('path', '')}
    elif name == 'get_diff':
        metadata = {'format': 'diff'}
    add(state, source, kind, content, **metadata)
    return {**result, 'evidence_id': source}


def check_quote(content, quote):
    """Match check text inside a JSON value without depending on wire escaping."""
    try:
        value = json.loads(content)
    except (ValueError, TypeError):
        return None
    try:
        if json.loads(quote) == value:
            return content  # Same complete record, different JSON formatting.
    except (ValueError, TypeError):
        pass
    def contains(value):
        if isinstance(value, str):
            return quote in value
        if isinstance(value, list):
            return any(contains(item) for item in value)
        if isinstance(value, dict):
            return any(contains(item) for item in value.values())
        return False
    # Do not join fields, interpret arbitrary escapes in quotes, or normalize
    # source code. The excerpt must occur literally in one delivered check value.
    return quote if contains(value) else None


def code_segments(source_id, source):
    """Remove only controller display gutters, never code whitespace or words.

    Older saved reviews lack format metadata. Recognize their complete numbered
    read windows and unified diffs conservatively so Resume can reuse evidence.
    Hunk/file boundaries stay separate; old and new sides are never spliced.
    """
    content = source['content']
    format_ = source.get('format')
    if format_ == 'numbered' or (not format_ and source_id.startswith('read:')):
        lines = content.splitlines(keepends=True)
        matches = [re.match(r'([1-9][0-9]*): ', line) for line in lines]
        if lines and all(matches):
            numbers = [int(match[1]) for match in matches]
            if numbers == list(range(numbers[0], numbers[0] + len(numbers))):
                yield ''.join(line[match.end():] for line, match in zip(lines, matches))
                return
    if format_ == 'diff' or (not format_ and (
            source_id == 'diff' or content.startswith('diff --git '))):
        old, new, in_hunk = [], [], False
        for line in content.splitlines(keepends=True):
            if re.match(r'^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@', line):
                yield ''.join(old); yield ''.join(new)
                old, new, in_hunk = [], [], True
            elif in_hunk and line[:1] in {' ', '+', '-'}:
                if line[0] != '+': old.append(line[1:])
                if line[0] != '-': new.append(line[1:])
            else:
                yield ''.join(old); yield ''.join(new)
                old, new, in_hunk = [], [], False
        yield ''.join(old); yield ''.join(new)


def matched_quote(source_id, source, quote):
    if not source or not isinstance(quote, str) or not quote.strip():
        return None
    if quote in source['content']:
        return quote
    if source['kind'] == 'check':
        return check_quote(source['content'], quote)
    if source['kind'] == 'code' and any(quote in segment for segment in code_segments(source_id, source)):
        return quote
    return None


class EvidenceError(ValueError):
    """All actionable corrections from one response, grounded in saved sources."""
    def __init__(self, issues, state):
        super().__init__('; '.join(issue['error'] for issue in issues))
        self.correction = {
            'code': 'review_evidence_missing', 'issues': issues,
            'next_action': 'Correct every listed response field and resubmit the complete review decision. Reuse the delivered evidence IDs; read only genuinely missing context. A formatting error is not a code defect or a reason to rerun passing checks. Do not approve unsupported claims.',
            'review_evidence': display(state)}


def validate(state, result):
    """Reject unsupported positive claims, never manufacture review evidence."""
    from .branch_disagreement import decision
    result.pop('_review_evidence', None)
    if decision(result, takeover=True) != 'APPROVE':
        return
    issues = []
    def issue(field, error, **details):
        issues.append({'field': field, 'error': error, **details})
    if not isinstance(result.get('feedback'), str) or not result['feedback'].strip():
        issue('feedback', 'Approval needs a nonempty explanation of the actual change.')
    assessment = result.get('review_assessment')
    if not isinstance(assessment, dict) or set(assessment) != {'criteria', 'regressions', 'verification', 'limitations'}:
        issue('review_assessment', 'Supply review_assessment with criteria, regressions, verification and limitations.')
    assessment = assessment if isinstance(assessment, dict) else {}
    claims = assessment.get('criteria')
    if not isinstance(claims, dict) or set(claims) != set(state['criteria']):
        issue('review_assessment.criteria', 'Assess every exact criterion: ' + json.dumps(state['criteria']))
    claims = claims if isinstance(claims, dict) else {}
    excerpts = {}
    def claim(value, label, field, implementation=False, verification=False):
        if not isinstance(value, dict) or not isinstance(value.get('reason'), str) or not value['reason'].strip():
            issue(field + '.reason', label + ' needs a reason grounded in the cited evidence.')
        if not isinstance(value, dict):
            return
        citations = value.get('citations')
        if not isinstance(citations, list) or not citations:
            issue(field + '.citations', label + ' needs exact evidence citations. Reuse delivered sources; read only missing evidence.')
            return
        kinds = set()
        for index, ref in enumerate(citations):
            location = field + f'.citations[{index}]'
            if not isinstance(ref, dict) or not isinstance(ref.get('source'), str):
                issue(location, 'Each citation needs a source ID and literal quote.')
                continue
            source = state['sources'].get(ref['source'])
            quote = matched_quote(ref['source'], source, ref.get('quote'))
            if quote is None:
                matches = [key for key, value in state['sources'].items()
                           if matched_quote(key, value, ref.get('quote')) is not None]
                issue(location, 'Citation not found in delivered current-candidate evidence: ' + ref['source'],
                      matching_source_ids=matches,
                      instruction='Use a matching source ID only if it supports your claim; otherwise quote the actual source or inspect missing context.')
                continue
            kinds.add(source['kind'])
            entry = excerpts.setdefault(ref['source'], {'kind': source['kind'], 'content': '', 'source_digest': source['digest']})
            if quote not in entry['content']:
                entry['content'] += ('\n' if entry['content'] else '') + quote
        if implementation and not state['partial'] and not kinds.intersection({'code', 'image'}):
            issue(field + '.citations', label + ' needs code/document or visual evidence; passing checks and prior approvals alone are insufficient.')
        if verification and not state['partial'] and any(s['kind'] == 'check' for s in state['sources'].values()) and 'check' not in kinds:
            issue(field + '.citations', 'Verification assessment must cite the actual check evidence and explain its coverage/limitations.')
    for key in state['criteria']:
        claim(claims.get(key), key, 'review_assessment.criteria.' + key, implementation=True)
    claim(assessment.get('regressions'), 'Regression assessment', 'review_assessment.regressions', implementation=True)
    claim(assessment.get('verification'), 'Verification assessment', 'review_assessment.verification', verification=True)
    limitations = assessment.get('limitations')
    if not isinstance(limitations, list) or any(not isinstance(v, str) or not v.strip() for v in limitations):
        issue('review_assessment.limitations', 'limitations must be an array of concrete verification limitations; use [] when none remain.')
    if issues:
        raise EvidenceError(issues, state)
    # Model-supplied receipts cannot survive this assignment.
    result['_review_evidence'] = {'version': VERSION, 'scope': state['scope'],
        'assessment_digest': digest(assessment), 'excerpts': excerpts}


def retained(result, scope):
    proof = result.get('_review_evidence', {})
    if not isinstance(proof, dict) or proof.get('version') != VERSION or proof.get('scope') != scope or proof.get('assessment_digest') != digest(result.get('review_assessment')):
        raise ValueError('Review evidence is missing or belongs to a different candidate.')


def visible_feedback(result):
    """Expose acknowledged verification limits in the existing review message."""
    text = result.get('feedback', '')
    proof, assessment = result.get('_review_evidence'), result.get('review_assessment')
    if not isinstance(proof, dict) or proof.get('version') != VERSION or not isinstance(assessment, dict):
        return text
    limits = assessment.get('limitations', [])
    if not isinstance(limits, list) or any(not isinstance(value, str) for value in limits):
        return text
    return text + ('\n\nVerification limitations:\n' + '\n'.join('- ' + value for value in limits) if limits else '')


def feedback(error, state):
    return {'error': str(error), 'code': 'review_evidence_missing',
            'next_action': 'Correct the response using delivered evidence. Read only missing context. Do not change code or claim a defect merely to satisfy this response contract.',
            'review_evidence': display(state), **getattr(error, 'correction', {})}


def handoff(engine, runtime, checkpoint, *, rejected=True):
    """Repeated unsupported approvals change reviewer, not operator allowance."""
    from .model_pool import automatic
    task = runtime.task
    model = (task.get('providers', {}).get('reviewer') or {}).get('model', '')
    failures = checkpoint.setdefault('evidence_failures', {})
    if rejected:
        failures[model] = failures.get(model, 0) + 1
    engine.store.save(task)
    runtime.failed_models.update(checkpoint.get('failed_reviewers', []))
    if failures.get(model, 0) < 3:
        return False
    if not automatic(task, 'reviewer'):
        from .branch_disagreement import invalid_review
        raise invalid_review('The selected reviewer repeatedly approved without supporting evidence. '
                             'Automatic replacement is not authorized for this model choice. '
                             'Saved changes and checks are retained; choose another reviewer or supply missing evidence.')
    runtime.guard()
    if runtime.stop.is_set():
        raise InterruptedError('Task stopped')
    if model not in checkpoint.setdefault('failed_reviewers', []):
        checkpoint['failed_reviewers'].append(model)
    runtime.failed_models.update(checkpoint['failed_reviewers'])
    engine.store.save(task)
    from .routing import select_remote
    select_remote(engine, runtime, 'reviewer', replace=True)
    checkpoint.setdefault('review_history', []).append(copy.deepcopy(checkpoint.get('messages', [])))
    checkpoint['messages'] = []
    engine.event(task, 'reviewer_recovery', 'Continuing evidence review with another reviewer',
                 {'from': model, 'role': 'reviewer', 'summary': 'Saved changes and checks are retained. The previous approval lacked supporting evidence.'})
    engine.store.save(task)
    return True
