import copy
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from cheapos import branch_workspace as bw
from cheapos.workspace import git


class BranchWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / 'source'
        self.source.mkdir()
        git(self.source, 'init', '-q', '-b', 'main')
        git(self.source, 'config', 'user.name', 'Test')
        git(self.source, 'config', 'user.email', 'test@example.invalid')
        (self.source / 'hello').write_bytes(b'hello\n\xff\n')
        (self.source / 'script').write_text('#!/bin/sh\ntrue\n')
        (self.source / 'script').chmod(0o755)
        (self.source / '.env').write_text('secret-not-copied')
        (self.source / 'link').symlink_to('hello')
        git(self.source, 'add', '.')
        git(self.source, 'commit', '-qm', 'base')
        self.destination = self.root / 'state/tasks/one/workspace'
        self.saved = []

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self, **kw):
        args = dict(source=self.source, destination=self.destination, base_ref='refs/heads/main',
                    feature_ref='refs/heads/feature/test', target_ref='refs/heads/main', run_id='run-one')
        args.update(kw)
        return bw.prepare(**args)

    def save(self, plan):
        self.saved.append(copy.deepcopy(plan))

    def test_dirty_source_and_linked_worktree_untouched_binary_modes_and_exclusions(self):
        linked = self.root / 'linked'
        git(self.source, 'worktree', 'add', '-qb', 'operator', str(linked))
        (self.source / 'hello').write_bytes(b'staged')
        git(self.source, 'add', 'hello')
        (self.source / 'hello').write_bytes(b'dirty')
        (self.source / 'untracked').write_text('local')
        before = (git(self.source, 'rev-parse', 'HEAD'), git(self.source, 'write-tree'), git(self.source, 'status', '--porcelain'))
        result = bw.create(self.prepare(), self.save)
        self.assertEqual(before, (git(self.source, 'rev-parse', 'HEAD'), git(self.source, 'write-tree'), git(self.source, 'status', '--porcelain')))
        self.assertEqual((self.destination / 'hello').read_bytes(), b'hello\n\xff\n')
        self.assertTrue((self.destination / 'script').stat().st_mode & 0o111)
        self.assertFalse((self.destination / '.env').exists())
        self.assertFalse((self.destination / 'link').exists())
        self.assertFalse((self.destination / 'untracked').exists())
        self.assertEqual(set(result['skipped']), {'.env', 'link'})
        self.assertEqual(git(self.source, 'show', 'feature/test:.env').strip(), 'secret-not-copied')
        self.assertTrue(bw.validate_owned(result))
        self.assertEqual(bw.create(result, self.save), result)
        # Reuse this repository fixture: a current update must preserve even the
        # source's dirty index, while rejecting dirty task copies/ownership drift.
        from cheapos.branch_update import prepare as update
        run={'workspace_mapping':result,'expected_feature_tip':result['feature_tip'],
             'target_ref':'refs/heads/main'}
        current=update(run)
        self.assertEqual(current['state'],'already_current');self.assertFalse(current['updated'])
        self.assertEqual(before, (git(self.source, 'rev-parse', 'HEAD'), git(self.source, 'write-tree'), git(self.source, 'status', '--porcelain')))
        (self.destination/'temporary').write_text('saved edit')
        with self.assertRaisesRegex(ValueError,'uncommitted'):update(run)
        self.assertEqual((self.destination/'temporary').read_text(),'saved edit')
        (self.destination/'temporary').unlink()
        git(self.source,'update-ref','-d',result['ownership_ref'])
        with self.assertRaisesRegex(ValueError,'ownership'):update(run)


    def test_branch_create_save_failure_recovers_with_git_ownership(self):
        def fail(plan):
            if plan['stage'] == 'branch_created':
                raise OSError('save failed')
            self.save(plan)
        with self.assertRaises(OSError):
            bw.create(self.prepare(), fail)
        result = bw.create(self.saved[-1], self.save)
        self.assertEqual(result['stage'], 'ready')
        git(self.source, 'update-ref', '-d', result['ownership_ref'])
        with self.assertRaisesRegex(ValueError, 'ownership'):
            bw.validate_owned(result)

    def test_existing_protected_invalid_and_changed_base_rejected(self):
        for name in ('main', 'refs/heads/main', 'refs/heads/bad..name'):
            with self.assertRaises(ValueError):
                self.prepare(feature_ref=name)
        git(self.source, 'branch', 'feature/test')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.prepare()
        git(self.source, 'branch', '-D', 'feature/test')
        plan = self.prepare()
        git(self.source, 'commit', '--allow-empty', '-qm', 'changed')
        with self.assertRaisesRegex(ValueError, 'Base changed'):
            bw.create(plan, self.save)

    def test_destination_filter_and_checked_out_owned_ref_rejected(self):
        with self.assertRaises(ValueError):
            self.prepare(destination=self.source / 'tasks/one/workspace')
        git(self.source, 'config', 'filter.custom.clean', 'cat')
        with self.assertRaisesRegex(ValueError, 'filters'):
            self.prepare()
        git(self.source, 'config', '--unset', 'filter.custom.clean')
        result = bw.create(self.prepare(), self.save)
        git(self.source, 'worktree', 'add', str(self.root / 'linked'), 'feature/test')
        with self.assertRaisesRegex(ValueError, 'checked out'):
            bw.validate_owned(result)

    def test_snapshot_limits_and_symlink_parent(self):
        with patch.object(bw, 'MAX_FILES', 1):
            with self.assertRaisesRegex(ValueError, 'too large'):
                self.prepare()
        alias = self.root / 'alias'
        alias.symlink_to(self.root / 'state')
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            self.prepare(destination=alias / 'tasks/one/workspace')
        (self.source / 'large').write_bytes(b'x' * 2_000_001)
        git(self.source, 'add', 'large')
        git(self.source, 'commit', '-qm', 'large')
        plan = self.prepare()
        self.assertIn('large', plan['skipped'])

    def test_replaced_source_and_unowned_identical_tip_fail(self):
        plan = self.prepare()
        moved = self.root / 'moved'
        self.source.rename(moved)
        self.source.mkdir()
        git(self.source, 'init', '-q', '-b', 'main')
        with self.assertRaisesRegex(ValueError, 'identity'):
            bw.create(plan, self.save)

    def test_marker_cannot_adopt_preexisting_identical_branch(self):
        plan = self.prepare()
        git(self.source, 'branch', 'feature/test')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            bw.create(plan, self.save)

    def test_materialize_preserves_source_refs_then_create_reuses_private_identity(self):
        plan = self.prepare()
        refs = git(self.source, 'show-ref')
        objects = sorted(str(p.relative_to(self.source / '.git/objects')) for p in (self.source / '.git/objects').rglob('*'))
        materialized = bw.materialize(plan, self.save)
        self.assertEqual(materialized['stage'], 'prepared')
        self.assertNotIn('ownership_oid', materialized)
        self.assertEqual(git(self.source, 'show-ref'), refs)
        self.assertEqual(sorted(str(p.relative_to(self.source / '.git/objects')) for p in (self.source / '.git/objects').rglob('*')), objects)
        self.assertEqual(bw.materialize(materialized, self.save), materialized)
        # A sibling task can merge while this proposal awaits approval. Keep
        # this same fixture to exercise actual Git ancestry and integration.
        (self.source / 'hello').write_bytes(b'newer task\n')
        git(self.source, 'add', 'hello')
        git(self.source, 'commit', '-qm', 'sibling task')
        current=git(self.source, 'rev-parse', 'HEAD').strip()
        result = bw.create(materialized, self.save)
        self.assertEqual(result['workspace_identity'], materialized['workspace_identity'])
        self.assertEqual(result['workspace_head'], materialized['workspace_head'])
        self.assertEqual(result['base_sha'],materialized['base_sha'])
        self.assertEqual(result['feature_tip'],materialized['base_sha'])
        self.assertEqual(git(self.source,'rev-parse','HEAD').strip(),current)
        self.assertEqual((self.source/'hello').read_bytes(),b'newer task\n')
        self.assertEqual((self.destination/'hello').read_bytes(),b'hello\n\xff\n')
        from cheapos import branch_merge
        with self.assertRaisesRegex(ValueError,'Target diverged'):
            branch_merge.prepare(result,result['feature_tip'],result['target_ref'])

    def test_modified_materialized_snapshot_blocks_source_ref_creation(self):
        plan = bw.materialize(self.prepare(), self.save)
        (self.destination / 'hello').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'clean'):
            bw.create(plan, self.save)
        self.assertIsNone(bw._tip(str(self.source), plan['feature_ref']))

    def test_configured_protected_ref_revalidated(self):
        plan = self.prepare()
        git(self.source, 'config', '--add', 'cheapos.protectedRef', 'refs/heads/feature/test')
        with self.assertRaisesRegex(ValueError, 'protected'):
            bw.create(plan, self.save)
        with self.assertRaisesRegex(ValueError, 'protected'):
            self.prepare()

    def test_partial_workspace_is_retained_and_not_adopted(self):
        plan = self.prepare()
        def fail(p):
            self.save(p)
            if p['stage'] == 'branch_created':
                self.destination.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'Partial workspace'):
            bw.create(plan, fail)
        self.assertTrue(self.destination.exists())
        self.assertTrue(bw._tip(str(self.source), plan['feature_ref']))

if __name__ == '__main__':
    unittest.main()
