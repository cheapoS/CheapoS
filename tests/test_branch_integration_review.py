"""One small Git comparison fixture; remaining cases use in-memory packets."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cheapos import branch_integration_review as review, branch_update, context_evidence
from cheapos.branch_authorization import digest
from cheapos.workspace import git


class IntegrationReviewTests(unittest.TestCase):
    def fixture(self):
        context = {'old_tip': 'parent', 'target_tip': 'captured-target', 'tree': 'suggested',
                   'conflicts': ['conflict.py']}
        key = digest(context)
        task = {'branch_run': {'expected_feature_tip': 'parent',
            'workspace_mapping': {'source': 'source', 'workspace': '/fixture', 'workspace_head': 'head'},
            'plan': {'items': [
                {'id': 'feature', 'title': 'Original work', 'instructions': 'Keep the feature',
                 'acceptance_criteria': ['Feature works']},
                {'id': 'resolve', 'instructions': key}]},
            'conflict_resolution': {'item_id': 'resolve', 'status': 'working',
                                    'context': context, 'context_digest': key}}}
        current = {'id': 'candidate', 'patch': 'full item patch', 'workspace': '/fixture',
            'private_baseline': 'head', 'context': {'item_id': 'resolve', 'feature_parent': 'parent'}}
        packet = {'candidate_id': current['id'], 'diff': current['patch'],
                  'checks': [{'candidate_id': current['id'], 'passed': True}],
                  'acceptance_criteria': ['Preserve both branches']}
        return task, current, packet

    def test_one_git_comparison_preserves_all_task_and_resolution_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git(root, 'init', '-q'); git(root, 'config', 'user.name', 'Fixture')
            git(root, 'config', 'user.email', 'fixture@example.invalid')
            for name in ('conflict.py', 'outside.py', 'script.sh'):
                (root / name).write_text('base\n')
            git(root, 'add', '.'); git(root, 'commit', '-qm', 'base')
            base = git(root, 'rev-parse', 'HEAD').strip()
            git(root, 'checkout', '-qb', 'feature')
            (root / 'conflict.py').write_text('task\n')
            (root / 'task-only.py').write_text('feature = True\n')
            git(root, 'add', '.'); git(root, 'commit', '-qm', 'task')
            parent = git(root, 'rev-parse', 'HEAD').strip()
            git(root, 'checkout', '-qb', 'target', base)
            (root / 'conflict.py').write_text('incoming\n')
            incoming = '# imported baseline\n' * 4000
            (root / 'incoming.py').write_text(incoming)
            (root / 'missing.py').write_text('must_keep = True\n')
            git(root, 'add', '.'); git(root, 'commit', '-qm', 'incoming')
            target = git(root, 'rev-parse', 'HEAD').strip()
            suggested, conflicts = branch_update.merge_candidate(str(root), parent, target)
            self.assertEqual(conflicts, ['conflict.py'])
            git(root, 'checkout', '-q', 'feature')
            (root / 'conflict.py').write_text('task and incoming\n')
            (root / 'incoming.py').write_text(incoming)
            (root / 'outside.py').write_text('unexpected edit\n')
            (root / 'script.sh').chmod(0o755)
            git(root, 'add', '.')
            patch_text = git(root, 'diff', '--cached', '--binary')
            index_before = git(root, 'write-tree')
            tree, delta, departures = review.comparisons(str(root), parent, patch_text, target,
                                                        suggested, {'skipped': []})
            self.assertNotIn('diff --git a/incoming.py', delta + departures)
            self.assertIn('task-only.py', delta)  # Earlier task work, absent from the item patch.
            self.assertNotIn('task-only.py', patch_text)
            for part in (delta, departures):
                self.assertIn('missing.py', part)  # A missing incoming file is never omitted.
                self.assertIn('outside.py', part)
                self.assertIn('conflict.py', part)
                self.assertIn('new mode 100755', part)
            self.assertIn('<<<<<<<', departures)  # Inspect the actual conflict resolution.
            self.assertEqual(git(root, 'rev-parse', 'HEAD').strip(), parent)
            self.assertEqual(git(root, 'write-tree'), index_before)
            self.assertEqual(git(root, 'diff', '--cached', '--binary'), patch_text)
            self.assertLess(len(delta + departures), len(patch_text) // 10)
            # Choosing the target wholesale can lose an earlier task change.
            (root / 'task-only.py').unlink(); git(root, 'add', '.')
            _, delta, departures = review.comparisons(str(root), parent,
                git(root, 'diff', '--cached', '--binary'), target, suggested, {'skipped': []})
            self.assertNotIn('task-only.py', delta)
            self.assertIn('task-only.py', departures)
            self.assertIn('-feature = True', departures)

    @patch.object(review.branch_workspace, 'validate_owned')
    @patch.object(review, 'comparisons', return_value=('tree', 'task against target', 'merge departures'))
    def test_packet_keeps_full_candidate_checks_requirements_and_frozen_target(self, comparisons, owned):
        task, current, packet = self.fixture()
        before = copy.deepcopy((current, packet))
        result = review.prepare(task, current, packet)
        self.assertEqual(result['diff'], 'task against target')
        self.assertEqual(result['checks'], packet['checks'])
        self.assertEqual(result['candidate_id'], current['id'])
        self.assertEqual(result['integration_review']['original_requirements'][0]['acceptance_criteria'], ['Feature works'])
        self.assertEqual(result['integration_review']['resolution_diff'], 'merge departures')
        self.assertEqual((current, packet), before)
        self.assertEqual(comparisons.call_args.args[3], 'captured-target')
        full = result['integration_review']['full_item_diff_reference']
        self.assertEqual(json.loads(context_evidence.read(task, full)['content'])['diff'], current['patch'])
        decision = {'integration_review': {'target_tip': 'model-invented'}}
        review.bind(decision, result, current)
        self.assertEqual(decision['integration_review']['target_tip'], 'captured-target')
        self.assertEqual(decision['integration_review']['full_patch_digest'], digest(current['patch']))
        self.assertEqual(json.loads(context_evidence.read(task, result['review_packet_reference'])['content'])['diff'], result['diff'])
        packet['repair_diff_since_claim'] = current['patch']
        repaired = review.prepare(task, current, packet)
        self.assertNotIn('repair_diff_since_claim', repaired)
        self.assertEqual(repaired['repair_diff_since_claim_evidence']['reference'], full)

    @patch.object(review.branch_workspace, 'validate_owned')
    @patch.object(review, 'comparisons')
    def test_resume_keeps_started_packet_but_changed_evidence_gets_new_comparison(self, comparisons, owned):
        task, current, packet = self.fixture()
        context_evidence.retain(task, packet, 'item_review_packet')
        restored = json.loads(json.dumps(task))
        self.assertEqual(review.prepare(restored, current, packet), packet)
        comparisons.assert_not_called()
        comparisons.return_value = ('tree', 'new diff', 'new resolution')
        changed = {**current, 'id': 'changed', 'patch': 'new complete patch'}
        new_packet = {**packet, 'candidate_id': 'changed', 'diff': changed['patch']}
        self.assertEqual(review.prepare(restored, changed, new_packet)['diff'], 'new diff')
        comparisons.assert_called_once()

    @patch.object(review.branch_workspace, 'validate_owned')
    @patch.object(review, 'comparisons')
    def test_changed_binding_blocks_projection_and_ordinary_review_is_unchanged(self, comparisons, owned):
        task, current, packet = self.fixture()
        for field in ('private_baseline', 'workspace'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                review.prepare(task, {**current, field: 'changed'}, packet)
        task['branch_run']['conflict_resolution']['context']['target_tip'] = 'tampered'
        with self.assertRaises(ValueError): review.prepare(task, current, packet)
        comparisons.assert_not_called()
        self.assertIs(review.prepare({}, current, packet), packet)
        decision = {'integration_review': {'candidate_id': 'model-invented'}}
        review.bind(decision, packet, current)
        self.assertNotIn('integration_review', decision)
