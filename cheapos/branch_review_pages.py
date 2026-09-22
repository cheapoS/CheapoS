"""Review oversized item packets exhaustively before ordinary criterion approval.

Packet size controls each request, never the amount of authorized branch work.
The existing packet reviewer supplies durable coverage, handoffs and usage gates.
"""
import copy
import hashlib
import json

from . import branch_evidence as evidence, context_evidence, review_context
from .branch_final import _review, check_sources
from .workspace import Workspace


def unchanged(task, current):
    if evidence.candidate(task, current['context'], current['check_specifications'], current['criteria']) != current:
        from .branch_pause import PauseError
        raise PauseError('branch_drift', stage='reviewing')


def read_candidate(task, current, manifest, args):
    if set(args) - {'manifest_id', 'path', 'start_line', 'end_line'} or args.get('manifest_id') != manifest['id']:
        raise ValueError('Context requires this exact item manifest identity.')
    unchanged(task, current)
    workspace = Workspace(current['workspace'])
    path = args.get('path')
    target = workspace.path(path)
    provenance = {'manifest_id': manifest['id'], 'candidate_id': current['id'], 'path': path}
    if not target.exists():
        return {**provenance, 'available': False, 'reason': 'File absent from this candidate.'}
    excerpt = workspace.read_file(path, args.get('start_line', 1), args.get('end_line'))
    unchanged(task, current)
    return {**excerpt, **provenance, 'available': True}


def prepare(engine, runtime, current, packet):
    """Return a bounded synthesis packet, complete coverage, or a real defect."""
    task = runtime.task
    reference = context_evidence.retain(task, packet, 'item_review_packet')
    text = task['context_evidence'][reference]['text']
    manifest = {'kind': 'item', 'candidate_id': current['id'],
                'requirements': [{'id': c, 'criterion': c} for c in current['criteria']]}
    manifest['id'] = evidence._digest({**manifest, 'packet_reference': reference})
    coverage = {'manifest_id': manifest['id'], 'candidate_id': current['id'],
                'packet_reference': reference, 'characters': len(text), 'chunks': []}
    parts = review_context.chunks(text, 12000)
    basis = packet.get('integration_review')
    comparison = ({key: copy.deepcopy(basis[key]) for key in
                   ('candidate_id', 'task_tip', 'target_tip', 'instruction')} if basis else None)
    task['status'] = 'reviewing'
    engine.event(task, 'review_paging', 'Reviewing the large item in smaller packets', {
        'item_id': current['context']['item_id'], 'candidate_id': current['id'],
        'packets': len(parts), 'characters': len(text)})
    engine.store.save(task)
    offset = 0
    for index, content in enumerate(parts, 1):
        unchanged(task, current)
        chunk = {'id': f'item:{index}', 'digest': hashlib.sha256(content.encode()).hexdigest(),
                 'start': offset, 'end': offset + len(content), 'content': content}
        part = {'manifest_id': manifest['id'], 'chunk_ids': [chunk['id']], 'criteria_ids': [],
                'check_output_sources': check_sources(packet),
                'chunk': chunk, 'acceptance_criteria': current['criteria'], 'full_evidence_reference': reference,
                'instruction': 'Review this part of the complete item evidence, including edits, checks and scope. '
                'Serialized JSON may begin or end mid-record; all other parts are reviewed separately. '
                'Do not reject solely because related evidence appears in a different part. '
                'Read surrounding candidate source or frozen merge evidence when needed. '
                'Approval covers only this part. A separate item decision must still verify every criterion.'}
        if comparison:
            part['integration_comparison'] = comparison
        review = _review(engine, runtime, manifest, part, [chunk['id']], [],
                         progress={'chunk_index': index, 'chunk_total': len(parts)},
                         context_reader=lambda args: read_candidate(task, current, manifest, args))
        unchanged(task, current)
        if review['decision'] != 'APPROVE':
            task['branch_run'].pop('active_final_review', None)
            return None, None, {**review, 'candidate_id': current['id']}
        coverage['chunks'].append({k: v for k, v in chunk.items() if k != 'content'} | {'review': review})
        offset = chunk['end']
    validate(coverage, current, task['providers']['worker'])
    task['branch_run'].pop('active_final_review', None)
    coverage_reference = context_evidence.retain(task, coverage, 'item_review_coverage')
    # Every byte above has received independent review. Keep large fields and
    # review feedback available through the existing paged evidence read tool;
    # never pretend an omitted diff means there were no changes.
    compact = {}
    for key, value in packet.items():
        if key == 'diff' or len(json.dumps(value)) > 6000:
            compact[key + '_evidence'] = {'reference': reference, 'field': key,
                'retrieve': 'Use read_context_evidence with this reference and search or offset.'}
        else:
            compact[key] = copy.deepcopy(value)
    compact['packet_coverage'] = {'reference': coverage_reference, 'packets_reviewed': len(parts),
        'candidate_id': current['id'], 'manifest_id': manifest['id'], 'all_parts_approved': True}
    if comparison:
        compact['integration_comparison'] = comparison
    compact['instruction'] = ('Synthesize the independently reviewed complete evidence against every acceptance '
        'criterion. Use read_context_evidence to retrieve full fields and packet feedback, and source tools '
        'to verify behavior as needed. Packet approvals do not establish criterion completion. '
        'Return the normal review_decision with exact candidate_id and evidence for each criterion.')
    engine.store.save(task)
    return compact, coverage, None


def validate(coverage, current, worker):
    """Receipt coverage must be complete, ordered, candidate-bound and independent."""
    if coverage.get('candidate_id') != current['id'] or not coverage.get('chunks'):
        raise ValueError('Item packet coverage belongs to a different or empty candidate.')
    offset = 0
    for index, chunk in enumerate(coverage['chunks'], 1):
        review = chunk['review']
        from .branch_disagreement import decision
        decision(review)
        if (chunk['id'] != f'item:{index}' or chunk['start'] != offset or chunk['end'] <= offset
                or review.get('manifest_id') != coverage['manifest_id']
                or review.get('chunk_ids') != [chunk['id']] or review.get('criteria_ids') != []
                or review.get('decision') != 'APPROVE'):
            raise ValueError('Independent item packet coverage is incomplete.')
        if evidence.model_identity(review.get('reviewer_model')) == evidence.model_identity(worker):
            raise ValueError('Item packet reviewer is not independent.')
        offset = chunk['end']
    if offset != coverage['characters']:
        raise ValueError('Independent item packet coverage is incomplete.')
