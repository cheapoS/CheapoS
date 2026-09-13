"""Tests for workspace and engine checkpoint rollback."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cheapos.workspace import Workspace
from test_engine import LocalCase


class RollbackTests(LocalCase):
    def test_workspace_rollback_to_patch(self):
        task = self.fixture()
        ws = Workspace(task['workspace'])

        # Read original file
        original = ws.read_file('math_utils.py')['content']

        # Edit 1: modify file
        ws.replace_text('math_utils.py', 'return min(value, upper)', 'return max(lower, min(value, upper))')
        patch_1 = ws.patch()
        self.assertIn('max(lower', patch_1)

        # Edit 2: create new file and make another edit
        ws.write_file('notes.txt', 'checkpoint 2 notes\n')
        ws.replace_text('math_utils.py', 'return max(lower, min(value, upper))', 'return 42')
        patch_2 = ws.patch()
        self.assertIn('notes.txt', patch_2)
        self.assertIn('return 42', patch_2)

        # Rollback to patch_1
        ws.rollback_to_patch(patch_1)
        self.assertFalse(ws.path('notes.txt').exists())
        self.assertEqual(ws.patch(), patch_1)
        self.assertIn('max(lower', ws.read_file('math_utils.py')['content'])

        # Rollback to baseline (empty patch)
        ws.rollback_to_patch('')
        self.assertEqual(ws.patch(), '')
        self.assertEqual(ws.read_file('math_utils.py')['content'], original)
        self.assertFalse(ws.path('notes.txt').exists())

    def test_engine_rollback_checkpoint(self):
        task = self.fixture()
        ws = Workspace(task['workspace'])

        # Create checkpoint 1
        ws.write_file('feature.py', 'def feat(): return True\n')
        self.engine.refresh_changes(task)
        cp1 = {
            'number': 1,
            'diff': task['patch'],
            'worker_summary': 'Added feature.py',
            'decision': 'APPROVE',
            'feedback': 'Good feature'
        }
        task['checkpoints'].append(cp1)
        self.engine.store.save(task)

        # Create checkpoint 2 (modifies feature and adds broken file)
        ws.write_file('broken.py', 'syntax error here\n')
        ws.replace_text('feature.py', 'return True', 'return False')
        self.engine.refresh_changes(task)
        cp2 = {
            'number': 2,
            'diff': task['patch'],
            'worker_summary': 'Broke feature and added broken.py',
            'decision': 'REQUEST_CHANGES',
            'feedback': 'Broken tests'
        }
        task['checkpoints'].append(cp2)
        self.engine.store.save(task)

        self.assertTrue(ws.path('broken.py').exists())

        # Rollback to checkpoint 1
        updated = self.engine.rollback_checkpoint(task['id'], 1)
        self.assertEqual(updated['patch'], cp1['diff'])
        self.assertFalse(ws.path('broken.py').exists())
        self.assertTrue(ws.path('feature.py').exists())
        self.assertIn('return True', ws.read_file('feature.py')['content'])
        self.assertEqual(len(updated['changes']), 1)
        self.assertEqual(updated['changes'][0]['path'], 'feature.py')

        # Check event was logged
        last_event = updated['events'][-1]
        self.assertEqual(last_event['title'], 'Rolled back workspace to Checkpoint #1')

        # Rollback to baseline (checkpoint 0)
        reset = self.engine.rollback_checkpoint(task['id'], 0)
        self.assertEqual(reset['patch'], '')
        self.assertEqual(len(reset['changes']), 0)
        self.assertFalse(ws.path('feature.py').exists())

    def test_engine_rollback_validations(self):
        task = self.fixture()

        # Non-integer checkpoint
        with self.assertRaisesRegex(ValueError, 'Provide a checkpoint number'):
            self.engine.rollback_checkpoint(task['id'], 'one')

        # Non-existent checkpoint
        with self.assertRaisesRegex(ValueError, 'Checkpoint #99 not found'):
            self.engine.rollback_checkpoint(task['id'], 99)


if __name__ == '__main__':
    unittest.main()
