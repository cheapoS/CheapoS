import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from cheapos import commits
from cheapos.engine import Engine
from cheapos.workspace import git
from commit_fixture import CommitCase


class CommitRecoveryTests(CommitCase):
    def test_failed_ref_update_preserves_staged_patch_and_recovers_after_restart(self):
        p = self.preview()
        real = commits.source_git
        def fail_ref(source, *args, **kwargs):
            if args[0] == 'update-ref':
                raise ValueError('Ref is locked')
            return real(source, *args, **kwargs)
        with patch.object(commits, 'source_git', side_effect=fail_ref):
            with self.assertRaisesRegex(ValueError, 'saved commit attempt'):
                self.approve(p)
        self.assertTrue((self.source / 'approved.txt').exists())
        self.assertEqual(git(self.source, 'rev-parse', 'HEAD').strip(), self.head)
        with self.assertRaisesRegex(ValueError, 'Finish the saved'):
            self.engine.start(self.task['id'])
        with self.assertRaisesRegex(ValueError, 'already approved and started'):
            self.engine.commit_decision(self.task['id'], {'decision':'defer','patch_digest':hashlib.sha256(p['patch'].encode()).hexdigest()})
        self.engine.shutdown()
        self.engine = Engine(Path(self.temp.name) / 'state')
        p = self.preview()
        self.assertTrue(p['retry'])
        result = self.approve(p)
        self.assertEqual(self.approve(p), result)
        self.assertEqual(git(self.source, 'status', '--porcelain'), '')
        self.assertEqual(git(self.source, 'rev-list', '--count', 'HEAD').strip(), '2')

    def test_recovery_after_source_commit_does_not_commit_twice(self):
        p = self.preview()
        with patch.object(commits, 'advance_workspace', side_effect=ValueError('Interrupted')):
            with self.assertRaisesRegex(ValueError, 'Interrupted'):
                self.approve(p)
        self.assertEqual(git(self.source, 'rev-list', '--count', 'HEAD').strip(), '2')
        self.approve(self.preview())
        self.assertEqual(self.workspace.patch(), '')
        self.assertEqual(git(self.source, 'rev-list', '--count', 'HEAD').strip(), '2')

    def test_recovery_does_not_discard_intervening_user_edits(self):
        p = self.preview()
        with patch.object(commits, 'apply_and_commit', side_effect=ValueError('Interrupted')):
            with self.assertRaises(ValueError):
                self.approve(p)
        (self.source / 'personal.txt').write_text('keep me')
        with self.assertRaisesRegex(ValueError, 'uncommitted'):
            self.preview()
        self.assertEqual((self.source / 'personal.txt').read_text(), 'keep me')


if __name__ == '__main__':
    unittest.main()
