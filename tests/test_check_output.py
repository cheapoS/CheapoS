"""Real command output must be visible before a command exits, with bounded previews."""
import json
import os
import sys
import threading
import unittest

from cheapos.engine import Runtime
from cheapos.storage import Store
from cheapos.workspace import Workspace
from test_engine import LocalCase, wait_for


class CheckOutputCompletenessTests(unittest.TestCase):
    def test_preview_clipping_requires_controller_capture_receipt(self):
        from cheapos.check_output import complete_output
        preview = {'truncated': True, 'run_id': 'a' * 32,
                   'raw_output': {'bytes': 34000, 'truncated': False}}
        self.assertTrue(complete_output(preview))
        self.assertTrue(complete_output({'truncated': False}))
        for changes in ({'raw_output': None}, {'raw_output': {}},
                        {'raw_output': {'bytes': 34000, 'truncated': True}},
                        {'raw_output': {'bytes': 34000}},
                        {'raw_output': {'bytes': 0, 'truncated': False}},
                        {'raw_output': {'bytes': True, 'truncated': False}},
                        {'run_id': None}, {'run_id': '../outside'}):
            with self.subTest(changes=changes):
                self.assertFalse(complete_output({**preview, **changes}))
        self.assertFalse(complete_output({'truncated': False,
                                         'raw_output': {'bytes': 34000, 'truncated': True}}))


class CheckOutputTests(LocalCase):
    def test_stdout_stderr_and_split_utf8_arrive_before_exit(self):
        workspace = Workspace(self.fixture()['workspace'])
        stop, seen_first_byte, seen_character = threading.Event(), threading.Event(), threading.Event()
        results, previews = [], []
        command = [sys.executable, '-c', "import os,time;os.write(1,b'hello\\n');time.sleep(.3);os.write(2,b'\\xe2');time.sleep(.3);os.write(2,b'\\x9c\\x93\\n');time.sleep(10)"]

        def emit(text, truncated):
            previews.append(text)
            if 'hello' in text:
                seen_first_byte.set()
            if '✓' in text:
                seen_character.set()

        worker = threading.Thread(target=lambda: results.append(workspace.run_checks(command, stop, on_output=emit)))
        worker.start()
        try:
            self.assertTrue(seen_first_byte.wait(3))
            self.assertTrue(seen_character.wait(3))
            self.assertTrue(worker.is_alive(), 'Output should arrive while the command is still running')
        finally:
            stop.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0]['reason'], 'cancelled')
        self.assertEqual(results[0]['output'], 'hello\n✓\n')
        self.assertTrue(all('�' not in text for text in previews))

    def test_noisy_command_completes_with_bounded_preview_and_full_tail(self):
        workspace = Workspace(self.fixture()['workspace'])
        previews = [];raw=[]
        def captured(path,cut): raw.append((path.stat().st_size,path.read_bytes()[-4:],cut))
        result = workspace.run_checks([sys.executable, '-c', "import os;os.write(1,b'x'*2100000+b'TAIL')"], threading.Event(), on_output=lambda text, cut: previews.append((text, cut)), on_raw_file=captured)
        self.assertTrue(result['passed'])
        self.assertIsNone(result['reason'])
        self.assertTrue(result['truncated'])
        self.assertLessEqual(len(result['output']),32000)
        self.assertTrue(result['output'].endswith('TAIL'))
        self.assertEqual(raw,[(2100004,b'TAIL',False)])
        self.assertTrue(all(len(text) <= 32000 for text, _ in previews))
        self.assertEqual(previews[-1], (result['output'], True))

    def test_engine_publishes_then_saves_final_output_and_clears_live_state(self):
        task = self.fixture()
        task.update(status='running', check_command=[sys.executable, '-c', "import time;print('Verifying now');time.sleep(10)"])
        runtime = Runtime(task)
        failures = []

        def run():
            try:
                self.engine.checks(runtime)
            except InterruptedError:
                pass
            except Exception as exc:
                failures.append(exc)

        worker = threading.Thread(target=run)
        worker.start()
        try:
            wait_for(lambda: 'Verifying now' in (self.engine.store.get(task['id']).get('check_stream') or {}).get('output', ''))
            current = self.engine.store.get(task['id'])
            self.assertTrue(worker.is_alive())
            self.assertEqual(current['checks'], [])
            self.assertNotEqual(current['updated_at'], current['check_stream']['started_at'])
            # Token-sized output updates are ephemeral; a crash cannot restore a live command.
            saved = json.loads((self.engine.store.root / 'tasks' / task['id'] / 'task.json').read_text())
            self.assertEqual(saved['check_stream']['output'], '')
            loaded = Store(self.engine.store.root).get(task['id'])
            self.assertEqual(loaded['status'], 'interrupted')
            self.assertIsNone(loaded['check_stream'])
        finally:
            runtime.stop.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertFalse(failures)
        current = self.engine.store.get(task['id'])
        self.assertIsNone(current['check_stream'])
        self.assertEqual(current['checks'][-1]['output'], 'Verifying now\n')
        self.assertEqual(current['checks'][-1]['reason'], 'cancelled')
        from cheapos.check_output import raw
        self.assertEqual(raw(Store(self.engine.store.root),task['id'],current['checks'][-1]['run_id']),b'Verifying now\n')

    def test_publish_failure_does_not_leave_a_child_running(self):
        workspace = Workspace(self.fixture()['workspace'])
        child_pid = []

        def broken_publish(text, truncated):
            if text.strip():
                child_pid.append(int(text.strip()))
                raise RuntimeError('preview disconnected')

        with self.assertRaisesRegex(RuntimeError, 'preview disconnected'):
            workspace.run_checks([sys.executable, '-c', 'import os,time;print(os.getpid());time.sleep(10)'], threading.Event(), on_output=broken_publish)
        with self.assertRaises(ProcessLookupError):
            os.kill(child_pid[0], 0)
