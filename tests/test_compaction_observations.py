"""Compaction retains read-loop evidence; no repository or provider fixture."""
import json
from types import SimpleNamespace
import unittest

from cheapos.engine import Engine, record_observation


class CompactionObservationTests(unittest.TestCase):
    def setUp(self):
        self.files = []
        self.runtime = SimpleNamespace(task={}, file_observations={}, edit_versions={}, compact_context_ready=False)
        self.engine = SimpleNamespace(
            action_messages=lambda task: [{}, {'content': json.dumps({'current_files': self.files})}],
            remember_file_version=lambda runtime, file: None)

    def snapshot(self, content='1: unchanged', digest='same'):
        self.files = [{'path': 'spec.md', 'hash': digest, 'content': content}]
        Engine.compact_context(self.engine, self.runtime)

    def read(self, content='1: unchanged', digest='same'):
        return record_observation(self.runtime, 'read_file', {'path': 'spec.md'},
                                  {'hash': digest, 'content': content})

    def test_repeated_read_reaches_stop_threshold_despite_compaction_and_omission(self):
        counts = []
        for _ in range(3):
            self.snapshot()
            counts.append(self.read())
        self.assertEqual(counts, [2, 3, 4])
        self.files = []
        Engine.compact_context(self.engine, self.runtime)
        self.assertEqual(self.read(), 1)  # Recover omitted evidence once.
        self.assertEqual(self.read(), 5)

    def test_union_keeps_old_ranges_and_new_versions_or_unseen_lines_are_progress(self):
        self.assertEqual(self.read(), 1)
        self.assertEqual(self.read(), 2)
        self.snapshot('2: another line')
        self.assertEqual(self.read('1: unchanged\n2: another line'), 1)
        self.assertEqual(self.read('1: unchanged\n2: another line'), 3)
        self.assertEqual(self.read('3: newly read line'), 1)
        self.assertEqual(self.read('1: changed', 'new-version'), 1)
        self.snapshot('1: changed', 'new-version')
        self.assertEqual(self.read('1: changed', 'new-version'), 2)


if __name__ == '__main__': unittest.main()
