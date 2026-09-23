"""Candidate-bound review citations. Provenance is verified; model judgment is not.

Only the controller registers delivered evidence. A check passing or a previous
approval is never implementation evidence on its own. No new execution authority.
"""
from .instructions.runtime import text as instruction
import copy
import hashlib
import json
import re
import shlex
from .check_specs import same

VERSION = 1
INSTRUCTION = instruction('reviewer.assessment')


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
    if packet.get('repair_checks'):
        checks = (checks if isinstance(checks, list) else [checks] if checks else []) + packet['repair_checks']
    if checks:
        add(state, 'checks', 'check', json.dumps(checks, ensure_ascii=False, sort_keys=True))
    unit = packet.get('review_unit')
    if isinstance(unit, dict) and unit.get('version') == 1:
        state['criteria'] = list(criteria)
        state['assessment_fields'] = (['criteria'] if unit['kind'] == 'requirements' else
                                      ['regressions', 'verification', 'limitations'] if unit['kind'] == 'integration' else
                                      ['criteria', 'regressions', 'verification', 'limitations'])
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
    refresh_check_claims(state, packet)
    return state


def labeled_commands(criteria):
    """Only result-only labels; parsing a command does not authorize execution."""
    commands = {}
    for key, criterion in criteria.items():
        match = re.fullmatch(r'[\w./-]+ (?:tests passed|passed structural validation) \(([^()]+)\)\.?', criterion.strip()) if isinstance(criterion, str) else None
        if match:
            try:
                command = shlex.split(match[1].strip('`'))
            except ValueError:
                continue
            if command:
                commands[key] = command
    return commands


def refresh_check_claims(state, packet, *, criterion_check_specs=None):
    """Bind narrowly stated command-result claims to controller check receipts.

    This is deliberately a full match, not a keyword classifier: behavioral or
    mixed claims retain the code/visual requirement. The reviewer cannot choose
    the evidence type. Existing same-candidate reads and attempts are retained.
    """
    texts = {key: key for key in state['criteria']}
    texts.update({row['id']: row['criterion'] for row in packet.get('requirements', []) if row['id'] in texts})
    # Unit tests of a validator cannot prove it ran on real inputs.
    missing_commands = labeled_commands(texts)
    # A named result-only check can use the sole check explicitly required by
    # its approved item. This mapping comes from the controller, never the model
    # or whichever command happened to pass. Ambiguity stays unresolved.
    named = {}
    for key, specs in (criterion_check_specs or {}).items():
        criterion = texts.get(key)
        if (isinstance(criterion, str) and len(specs) == 1
                and re.fullmatch(r'(?:The )?(?:[\w-]+ ){1,4}check passes\.?', criterion.strip(), re.IGNORECASE)
                and not re.search(r'\b(?:and|or)\b', criterion, re.IGNORECASE)):
            named[key] = specs[0]
            missing_commands[key] = specs[0]['command']
    bindings = {key: [] for key in missing_commands}
    checks = packet.get('checks') or []
    if isinstance(checks, dict):
        checks = [checks]  # Interactive checkpoints carry one result.
    checks = checks + packet.get('repair_checks', [])
    for bound in checks:
        record = bound.get('record', bound)
        command = record.get('command', bound.get('command'))
        if (record.get('passed') is not True or record.get('exit_code') != 0 or record.get('reason')
                or not isinstance(command, list) or not command or any(not isinstance(arg, str) for arg in command)):
            continue
        # A result-only sentence cannot silently acquire extra behavioral claims.
        suffix = r'(?:passes(?: with zero diagnostics)?|completes without errors|outputs result PASS(?: with all assertions satisfied)?)\.?'
        pattern = r'`?' + re.escape(shlex.join(command)) + r'`?\s+' + suffix
        for key, criterion in texts.items():
            labeled = r'[\w./-]+ (?:tests passed|passed structural validation) \(`?' + re.escape(shlex.join(command)) + r'`?\)\.?'
            named_match = key in named and same(record, named[key]) and same(bound, named[key])
            if not isinstance(criterion, str) or not (named_match or re.fullmatch(pattern, criterion.strip()) or re.fullmatch(labeled, criterion.strip())):
                continue
            source = 'check:' + digest(bound)[:20]
            add(state, source, 'check', json.dumps(bound, ensure_ascii=False, sort_keys=True))
            bindings.setdefault(key, []).append(source)
    state['criterion_checks'] = bindings
    state['missing_criterion_checks'] = {key: command for key, command in missing_commands.items() if not bindings[key]}


def display(state):
    sources = []
    for source, value in state['sources'].items():
        row = {'id': source, 'kind': value['kind'], 'digest': value['digest']}
        row.update({key: value[key] for key in ('path', 'format') if key in value})
        if source.startswith('chunk:'):
            row['content'] = value['content']  # The synthesizer must see the cited code.
        sources.append(row)
    return {'version': VERSION, 'scope': state['scope'], 'criteria': state['criteria'], 'sources': sources,
            'criterion_checks': state.get('criterion_checks', {}),
            'missing_criterion_checks': state.get('missing_criterion_checks', {}),
            'instruction': instruction('reviewer.evidence_catalog')}


def citation(state, source, start, end):
    """Register the exact delivered span, bound to this candidate and source."""
    value = state['sources'][source]
    if start >= end or not value['content'][start:end].strip():
        return None
    record = {'source': source, 'source_digest': value['digest'], 'start': start, 'end': end}
    identity = 'excerpt:' + digest({'scope': state['scope'], **record})[:20]
    state.setdefault('excerpts', {})[identity] = record
    return {'source': source, 'excerpt_id': identity}


def cited_excerpt(state, ref):
    """Never accept caller-supplied offsets, content, or an old candidate's ID."""
    record = state.get('excerpts', {}).get(ref.get('excerpt_id'))
    source = state['sources'].get(ref.get('source'))
    if not record or not source or record['source'] != ref['source'] or record['source_digest'] != source['digest']:
        return None
    expected = 'excerpt:' + digest({'scope': state['scope'], **record})[:20]
    if ref['excerpt_id'] != expected:
        return None
    content = source['content'][record['start']:record['end']]
    if 'quote' in ref:
        return matched_quote(ref['source'], {**source, 'content': content}, ref['quote'])
    return content


def read(state, source=None, offset=0, search=None):
    """Page only this candidate's delivered evidence, including after handoff."""
    if source is None:
        return display(state)
    if isinstance(source, str) and source not in state['sources'] and re.fullmatch(r'[a-f0-9]{20}', source):
        matches = [key for key in state['sources'] if key.rsplit(':', 1)[-1] == source]
        if len(matches) == 1:
            source = matches[0]  # Recover an omitted prefix only for one exact current source.
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
            'citation': citation(state, source, offset, offset + len(page)),
            'instruction': instruction('reviewer.delivered_excerpt')}


def packet_for_model(packet):
    """Keep source excerpts in the catalog once; full receipts remain saved."""
    result = copy.deepcopy(packet)
    if packet.get('review_unit'):
        # Full coverage remains in complete_task_reference and the proof store.
        # Send source metadata once; exact small excerpts arrive with handles.
        result.pop('checks', None)  # Exact check excerpts/handles are delivered separately.
        result['chunk_coverage'] = [{'chunk_id': row.get('chunk_id'), 'digest': row.get('digest'),
                                     'decision': row.get('review', {}).get('decision')}
                                    for row in result.pop('coverage', [])]
        for row in result.get('review_evidence', {}).get('sources', []):
            row.pop('content', None)
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
        'excerpt_id': {'type': 'string', 'minLength': 1, 'description': 'Prefer the returned citation.excerpt_id from a read tool; copy its citation object unchanged. A quote is unnecessary; if supplied it must occur in that exact excerpt.'},
        'quote': {'type': 'string', 'minLength': 1, 'description': 'Short literal excerpt from this source. Preserve code whitespace; display line numbers/diff gutters are optional.'}},
                'required': ['source'], 'additionalProperties': False}
    claim = {'type': 'object', 'properties': {'reason': {'type': 'string', 'minLength': 1},
             'citations': {'type': 'array', 'minItems': 1, 'items': citation}}, 'required': ['reason', 'citations'], 'additionalProperties': False}
    criteria = {key: copy.deepcopy(claim) for key in state['criteria']}
    for key, sources in state.get('criterion_checks', {}).items():
        criteria[key]['description'] = ('Command-result-only claim. Cite its current check receipt: ' + ', '.join(sources) if sources else
            'No matching passing command receipt is available. Request the missing focused check; other checks or source code cannot prove this command passed.')
    result = {'type': 'object', 'description': 'Required for APPROVE. Supply all four fields; each claim needs a nonempty reason and citations. Use [] for no verification limitations.', 'properties': {
        'criteria': {'type': 'object', 'properties': criteria,
                     'required': state['criteria'], 'additionalProperties': False},
        'regressions': copy.deepcopy(claim), 'verification': copy.deepcopy(claim),
        'limitations': {'type': 'array', 'items': {'type': 'string'}}},
        'required': ['criteria', 'regressions', 'verification', 'limitations'], 'additionalProperties': False}
    fields = assessment_fields(state)
    result['properties'] = {k: v for k, v in result['properties'].items() if k in fields}
    result['required'] = fields
    return result


def assessment_fields(state):
    return state.get('assessment_fields', ['criteria', 'regressions', 'verification', 'limitations'])


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
    return {**result, 'evidence_id': source, 'citation': citation(state, source, 0, len(content))}


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


def assess_claim(state, value, label, field, *, issues, excerpts, implementation=False, verification=False, required_sources=None):
    def issue(field, error, **details):
        issues.append({"field": field, "error": error, **details})
    if not isinstance(value, dict) or not isinstance(value.get('reason'), str) or not value['reason'].strip():
        issue(field + '.reason', label + ' needs a reason grounded in the cited evidence.')
    if not isinstance(value, dict):
        return
    citations = value.get('citations')
    if not isinstance(citations, list) or not citations:
        issue(field + '.citations', label + ' needs exact evidence citations. Reuse delivered sources; read only missing evidence.')
        return
    kinds = set()
    matched_sources = set()
    for index, ref in enumerate(citations):
        location = field + f'.citations[{index}]'
        if not isinstance(ref, dict) or not isinstance(ref.get('source'), str):
            issue(location, 'Each citation needs a source ID and a returned excerpt_id or literal quote.')
            continue
        source = state['sources'].get(ref['source'])
        quote = cited_excerpt(state, ref) if isinstance(ref.get('excerpt_id'), str) else matched_quote(ref['source'], source, ref.get('quote'))
        if quote is None:
            canonical = {'source': ref['source'], 'excerpt_id': ref.get('excerpt_id')}
            if isinstance(ref.get('excerpt_id'), str) and cited_excerpt(state, canonical) is not None:
                issue(location, 'The excerpt reference is valid, but the supplied quote is not literal.',
                      citation=canonical, instruction=instruction('reviewer.correct_quote'))
                # Identify the actual evidence kind without accepting the bad
                # quote or saving an approval excerpt. The issue still rejects
                # this decision; only an explicit corrected response can pass.
                kinds.add(source['kind'])
                matched_sources.add(ref['source'])
                continue
            matches = [key for key, value in state['sources'].items()
                       if matched_quote(key, value, ref.get('quote')) is not None]
            issue(location, 'Citation not found in delivered current-candidate evidence: ' + ref['source'],
                  matching_source_ids=matches,
                  instruction=instruction('reviewer.correct_citation'))
            continue
        kinds.add(source['kind'])
        matched_sources.add(ref['source'])
        entry = excerpts.setdefault(ref['source'], {'kind': source['kind'], 'content': '', 'source_digest': source['digest']})
        if quote not in entry['content']:
            entry['content'] += ('\n' if entry['content'] else '') + quote
    if implementation and not state['partial'] and not kinds.intersection({'code', 'image'}):
        issue(field + '.citations', label + ' needs code/document or visual evidence; passing checks and prior approvals alone are insufficient.')
    if verification and not state['partial'] and any(s['kind'] == 'check' for s in state['sources'].values()) and 'check' not in kinds:
        issue(field + '.citations', 'Verification assessment must cite the actual check evidence and explain its coverage/limitations.')
    if required_sources is not None and not matched_sources.intersection(required_sources):
        issue(field + '.citations', 'Command-result claim must cite its matching current check receipt.', matching_source_ids=required_sources)


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
    fields = assessment_fields(state)
    if not isinstance(assessment, dict) or set(assessment) != set(fields):
        issue('review_assessment', 'Supply review_assessment with exactly: ' + ', '.join(fields))
    assessment = assessment if isinstance(assessment, dict) else {}
    claims = assessment.get('criteria', {} if 'criteria' not in fields else None)
    if not isinstance(claims, dict) or set(claims) != set(state['criteria']):
        issue('review_assessment.criteria', 'Assess every exact criterion: ' + json.dumps(state['criteria']))
    claims = claims if isinstance(claims, dict) else {}
    excerpts = {}
    def claim(value, label, field, **options):
        assess_claim(state, value, label, field, issues=issues, excerpts=excerpts, **options)
    for key in state['criteria']:
        sources = state.get('criterion_checks', {}).get(key)
        claim(claims.get(key), key, 'review_assessment.criteria.' + key, implementation=sources is None, required_sources=sources)
    if 'regressions' in fields: claim(assessment.get('regressions'), 'Regression assessment', 'review_assessment.regressions', implementation=True)
    if 'verification' in fields: claim(assessment.get('verification'), 'Verification assessment', 'review_assessment.verification', verification=True)
    limitations = assessment.get('limitations', [] if 'limitations' not in fields else None)
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
