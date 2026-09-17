"""Review a conflict resolution against its frozen incoming target.

The candidate and commit receipt still cover the complete item patch. Only the
review presentation changes: imported target code is background, while every
task change and every departure from Git's suggested combination is visible.
"""
import copy
import json
import tempfile
from pathlib import Path

from . import branch_conflicts, branch_evidence, branch_workspace, context_evidence
from .branch_commits import _preserve_exclusions


def comparisons(source, parent, patch, target, suggested, mapping):
    """Build immutable tree objects with a disposable index, never move refs."""
    git = branch_workspace.source_git
    with tempfile.TemporaryDirectory(prefix='cheapos-integration-review-') as directory:
        index = Path(directory) / 'index'
        git(source, 'read-tree', parent, index=index)
        if patch:
            git(source, 'apply', '--cached', '--whitespace=nowarn', '-', input=patch, index=index)
        tree = git(source, 'write-tree', index=index)
    _preserve_exclusions(source, parent, tree, mapping)
    def diff(base):
        return git(source, 'diff', '--binary', '--no-ext-diff', '--no-textconv', '--no-renames',
                   base, tree, '--', binary=True).decode('utf-8')
    return tree, diff(target), diff(suggested)


def prepare(task, current, packet):
    run = task.get('branch_run', {})
    resolution = run.get('conflict_resolution')
    if not resolution or resolution.get('item_id') != current['context']['item_id']:
        return packet
    resolution = branch_conflicts.current(task)
    context = resolution['context']
    parent = current['context']['feature_parent']
    mapping = run['workspace_mapping']
    if (resolution.get('status') != 'working' or parent != context['old_tip']
            or parent != run['expected_feature_tip']
            or current['private_baseline'] != mapping['workspace_head']
            or current['workspace'] != mapping['workspace']):
        raise ValueError('Conflict review no longer matches the captured task and target.')
    branch_workspace.validate_owned(mapping, parent)

    # A partly reviewed legacy packet stays identical on Resume. Optimization
    # must not discard valid page approvals or restart an in-flight review.
    for record in task.get('context_evidence', {}).values():
        if record.get('kind') == 'item_review_packet' and json.loads(record['text']) == packet:
            return packet

    tree, target_diff, resolution_diff = comparisons(mapping['source'], parent, current['patch'],
        context['target_tip'], context['tree'], mapping)
    full_patch = context_evidence.retain(task, {
        'candidate_id': current['id'], 'feature_parent': parent, 'diff': current['patch']
    }, 'integration_item_diff')
    original_requirements = [
        {key: copy.deepcopy(item[key]) for key in ('id', 'title', 'instructions', 'acceptance_criteria')}
        for item in run['plan']['items'] if item['id'] != resolution['item_id']
    ]
    result = {**packet, 'diff': target_diff, 'integration_review': {
        'candidate_id': current['id'], 'candidate_tree': tree,
        'task_tip': parent, 'target_tip': context['target_tip'],
        'context_digest': resolution['context_digest'],
        'conflict_paths': copy.deepcopy(context['conflicts']),
        'original_requirements': original_requirements,
        'resolution_diff': resolution_diff,
        'full_item_diff_reference': full_patch,
        'instruction': 'The main diff compares the complete candidate against the frozen incoming target. '
            'Unchanged target code is baseline, not new task work. The resolution_diff compares against '
            'Git\'s suggested merge and exposes dropped task work, missing incoming changes, and other '
            'departures, including changes outside conflict paths. Review both diffs and preserve the '
            'original requirements. An empty target diff is not proof that the task survived integration. '
            'Checks ran on the complete combined candidate; verify relevant interactions in current source '
            'and use read_merge_context for frozen versions. The full item diff remains available through '
            'read_context_evidence. All item criteria still require independent approval.'}}
    if result.get('repair_diff_since_claim') == current['patch']:
        result.pop('repair_diff_since_claim')
        result['repair_diff_since_claim_evidence'] = {'reference': full_patch,
            'description': 'Complete current item patch; the two integration diffs above show the current resolution.'}
    reference = context_evidence.retain(task, result, 'integration_review_packet')
    # Keep the controller-created input reference with the eventual decision.
    result['review_packet_reference'] = reference
    return result


def bind(review, packet, current):
    """Models cannot choose the recorded review basis."""
    review.pop('integration_review', None)
    basis = packet.get('integration_review')
    if basis:
        review['integration_review'] = {key: basis[key] for key in
            ('candidate_id', 'candidate_tree', 'task_tip', 'target_tip', 'context_digest')}
        review['integration_review'].update(packet_reference=packet['review_packet_reference'],
                                           full_patch_digest=branch_evidence._digest(current['patch']))
