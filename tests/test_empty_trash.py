import unittest
from cheapos.engine import Engine
from pathlib import Path
import tempfile
import shutil
import json

class TestEmptyTrash(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.engine = Engine(self.test_dir)
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_empty_trash(self):
        # Create a dummy task and trash it
        task = {"id": "task1", "title": "Test Task", "status": "completed", "created_at": "2026-09-13T00:00:00Z", "updated_at": "2026-09-13T00:00:00Z", "demo": False, "usage": {}, "source": "test"}
        self.engine.store.save(task)
        # Need to put something in metadata for trashed_at
        metadata = {"custom_title": "Test Task", "pinned": False, "archived_at": None, "trashed_at": "2026-09-13T00:00:00Z", "trash_archived_at": None}
        (Path(self.test_dir) / "tasks" / "task1").mkdir(parents=True, exist_ok=True)
        (Path(self.test_dir) / "tasks" / "task1" / "metadata.json").write_text(json.dumps(metadata))
        
        # Verify it's in trash
        trashed = self.engine.store.visible(view="trash")
        self.assertEqual(len(trashed), 1)
        
        # Empty trash
        self.engine.empty_trash()
        
        # Verify it's gone
        trashed_after = self.engine.store.visible(view="trash")
        self.assertEqual(len(trashed_after), 0)
        self.assertFalse((Path(self.test_dir) / "tasks" / "task1").exists())

if __name__ == '__main__':
    unittest.main()
