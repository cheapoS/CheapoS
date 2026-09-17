"""Tests for vision sidecar and inspect_image tool execution."""

import base64
import copy
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from cheapos.uploads import save_upload
from cheapos.vision import inspect_image_tool, resolve_image_path
from test_engine import LocalCase


class VisionResponsivenessTests(unittest.TestCase):
    """No providers, Git workflows, or timed sleeps; use a second thread as the UI."""

    def setUp(self):
        from cheapos.admission import Admission
        from cheapos.engine import Engine

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / 'image.png').write_bytes(b'\x89PNG\r\n\x1a\n')
        self.task = {'id': 'image', 'workspace': str(root), 'demo': False,
                     'status': 'running', 'active_role': 'worker', 'tool_actions': 0,
                     'providers': {'worker': {'model': 'fixture-vision'}}}
        self.runtime = SimpleNamespace(task=self.task, guard=Mock(), stop=threading.Event(),
                                       approval=threading.Event(), thread=Mock(is_alive=lambda: True))
        self.engine = Engine.__new__(Engine)
        self.engine.lock = threading.RLock()
        self.engine.store = SimpleNamespace(root=root)
        self.engine.event = Mock()
        self.engine.require_active_task = Mock()
        other = SimpleNamespace(task={'branch_run': {}}, thread=Mock(is_alive=lambda: True))
        self.engine.runtimes = {'image': self.runtime, 'other': other}
        self.engine.admission = Admission(self.engine)

    def operator_access(self, *, pause=False):
        observations = []
        def inspect():
            # Nonblocking acquisition makes the old bug fail immediately rather
            # than deadlocking the test or requiring a real timeout.
            acquired = self.engine.lock.acquire(blocking=False)
            observations.append(acquired)
            if acquired:
                try:
                    observations.append(len(self.engine.admission.snapshot()['active']))
                    if pause:
                        observations.append(self.engine.stop('image'))
                finally:
                    self.engine.lock.release()
        thread = threading.Thread(target=inspect)
        thread.start()
        thread.join()
        return observations

    def test_image_request_keeps_other_task_and_operator_accessible(self):
        observations = []
        def request(runtime, messages, tools, role, purpose):
            observations.extend(self.operator_access())
            self.assertIs(runtime, self.runtime)
            self.assertEqual((role, purpose, tools), ('worker', 'vision', []))
            return {'content': 'The image shows a diagram.'}
        self.engine._request = Mock(side_effect=request)

        result = self.engine.worker_file_tool(self.runtime, 'inspect_image', {'path': 'image.png'}, {})

        self.assertEqual(observations, [True, 2])
        self.assertEqual(result['analysis'], 'The image shows a diagram.')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(self.task['tool_actions'], 1)
        self.engine._request.assert_called_once()

    def test_pause_interrupts_image_inspection_without_fallback_success(self):
        observations = []
        def request(*args, **kwargs):
            observations.extend(self.operator_access(pause=True))
            if self.runtime.stop.is_set():
                raise InterruptedError('Image inspection paused')
            return {'content': 'Must not complete after Pause'}
        self.engine._request = Mock(side_effect=request)

        with self.assertRaisesRegex(InterruptedError, 'paused'):
            self.engine.worker_file_tool(self.runtime, 'inspect_image', {'path': 'image.png'}, {})

        self.assertEqual(observations, [True, 2, {'stopping': True}])
        self.assertEqual(self.task['status'], 'stopping')
        self.assertEqual(self.task['tool_actions'], 0)

    def test_file_mutations_keep_existing_lock(self):
        observations = []
        def edit(*args, **kwargs):
            observations.extend(self.operator_access())
            return {'written': True}
        self.engine.file_tool = Mock(side_effect=edit)
        self.runtime.edit_versions = {}

        result = self.engine.worker_file_tool(self.runtime, 'write_file', {'path': 'note.txt', 'content': 'ok'}, {})

        self.assertEqual(observations, [False])
        self.assertEqual(result, {'written': True})


class VisionToolTests(LocalCase):
    def test_resolve_image_path(self):
        ws_dir = self.engine.store.root / "workspace"
        ws_dir.mkdir(parents=True, exist_ok=True)
        img_file = ws_dir / "diagram.png"
        img_file.write_bytes(b"\x89PNG\r\n\x1a\n")

        # Sister directory with matching prefix: workspace-secret
        secret_dir = self.engine.store.root / "workspace-secret"
        secret_dir.mkdir(parents=True, exist_ok=True)
        canary_file = secret_dir / "canary.svg"
        canary_file.write_text("<svg><circle/></svg>")

        task = {"workspace": str(ws_dir), "attachments": []}
        # Resolve workspace relative
        resolved = resolve_image_path(task, "diagram.png", self.engine.store.root)
        self.assertEqual(resolved, img_file)

        # Prefix collision path traversal (finding 2) must be rejected
        escape = resolve_image_path(task, "../workspace-secret/canary.svg", self.engine.store.root)
        self.assertIsNone(escape)

        # Path traversal outside workspace rejected
        traversal = resolve_image_path(task, "../../secret.png", self.engine.store.root)
        self.assertIsNone(traversal)

    def test_inspect_image_svg(self):
        ws_dir = self.engine.store.root / "mock_workspace"
        ws_dir.mkdir(parents=True, exist_ok=True)
        svg_file = ws_dir / "button.svg"
        svg_file.write_text("<svg><rect width='100' height='30'/></svg>")

        task = {"workspace": str(ws_dir), "attachments": [], "demo": True}
        result = inspect_image_tool(self.engine, task, {"path": "button.svg", "query": "Check rect dimensions"})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["format"], "svg")
        self.assertIn("<rect width='100'", result["analysis"])

    def test_inspect_image_raster_mock(self):
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        record = save_upload(self.engine.store.root, "ui.png", base64.b64encode(png_bytes).decode("ascii"))

        task = {"workspace": str(self.engine.store.root), "attachments": [record], "demo": True}
        result = inspect_image_tool(self.engine, task, {"path": "ui.png", "query": "What is visible?"})
        self.assertEqual(result["status"], "mock")
        self.assertEqual(result["image"], "ui.png")
        self.assertIn("Visual inspection of ui.png", result["analysis"])

    def test_inspect_image_missing_and_non_image(self):
        task = {"workspace": str(self.engine.store.root), "attachments": [], "demo": True}
        res_missing = inspect_image_tool(self.engine, task, {"path": "missing.png"})
        self.assertIn("error", res_missing)

        txt_file = self.engine.store.root / "not_image.txt"
        txt_file.write_text("plain text")
        task["workspace"] = str(self.engine.store.root)
        res_txt = inspect_image_tool(self.engine, task, {"path": "not_image.txt"})
        self.assertIn("error", res_txt)

    def test_inspect_image_budget_exhaustion_and_accounting(self):
        from cheapos.providers import BudgetError
        from test_engine import CONFIG

        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        record = save_upload(self.engine.store.root, "button.png", base64.b64encode(png_bytes).decode("ascii"))

        class MockVisionProvider:
            def complete_brief(self, messages, tools, maximum, emit=None, stopped=None):
                return {"role": "assistant", "content": "Visual analysis completed"}, {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.05}
            def complete(self, messages, tools, maximum):
                return {"role": "assistant", "content": "Visual analysis completed"}, {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.05}

        self.engine.provider_factory = lambda role, config: MockVisionProvider()

        task = self.fixture(paid=True)
        task["attachments"] = [record]
        task["limits"]["dollars"] = 1.0
        task["usage"] = {"worker": {"tokens": 0, "cost": 0}, "reviewer": {"tokens": 0, "cost": 0}, "planner": {"tokens": 0, "cost": 0}, "cost": 0, "uncertain_requests": 0, "estimated_requests": 0}
        self.engine.store.save(task)

        # Budget exhausted: cost > limits["dollars"]
        task["usage"]["cost"] = 2.0
        self.engine.store.save(task)
        with self.assertRaises(BudgetError):
            inspect_image_tool(self.engine, task, {"path": "button.png", "query": "Analyze button"})

        # Budget ok: normal request routes through engine and reconciles usage & metrics
        task["usage"]["cost"] = 0.0
        self.engine.store.save(task)
        res = inspect_image_tool(self.engine, task, {"path": "button.png", "query": "Analyze button"})
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["analysis"], "Visual analysis completed")
        self.assertGreater(len(task.get("request_metrics", [])), 0)
        self.assertEqual(task["request_metrics"][-1]["purpose"], "vision")

    def test_unattended_vision_preserves_multimodal_payload_and_query(self):
        from cheapos.engine import Runtime

        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        record = save_upload(self.engine.store.root, "dialog.png", base64.b64encode(png_bytes).decode("ascii"))

        captured_calls = []

        class CapturingVisionProvider:
            def complete_brief(self, messages, tools, maximum, emit=None, stopped=None):
                captured_calls.append({"messages": copy.deepcopy(messages), "tools": tools})
                return {"role": "assistant", "content": "Dialog analysis: OK button is green"}, {"prompt_tokens": 120, "completion_tokens": 40, "cost": 0.01}
            def complete(self, messages, tools, maximum):
                captured_calls.append({"messages": copy.deepcopy(messages), "tools": tools})
                return {"role": "assistant", "content": "Dialog analysis: OK button is green"}, {"prompt_tokens": 120, "completion_tokens": 40, "cost": 0.01}

        self.engine.provider_factory = lambda role, config: CapturingVisionProvider()

        task = self.fixture(paid=True)
        task["attachments"] = [record]
        task["branch_run"] = {
            "id": "branch-run-1",
            "authorization_ref": "auth-unattended-trial-123",
            "items": [{"id": "item-1", "title": "Check dialog UI", "instructions": "inspect dialog", "acceptance_criteria": [], "required_checks": [], "status": "running"}],
            "current_item_id": "item-1",
            "status": "running",
        }
        self.engine.store.save(task)

        runtime = Runtime(task)
        res = inspect_image_tool(self.engine, task, {"path": "dialog.png", "query": "Is the OK button green?"}, runtime=runtime)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["analysis"], "Dialog analysis: OK button is green")

        # Verify the actual provider-bound messages preserved the multimodal payload
        self.assertEqual(len(captured_calls), 1)
        sent_messages = captured_calls[0]["messages"]
        self.assertEqual(len(sent_messages), 1)
        user_msg = sent_messages[0]
        self.assertEqual(user_msg["role"], "user")
        self.assertIsInstance(user_msg["content"], list)
        self.assertEqual(len(user_msg["content"]), 2)
        # Content item 0: text prompt with query
        self.assertEqual(user_msg["content"][0]["type"], "text")
        self.assertIn("Is the OK button green?", user_msg["content"][0]["text"])
        # Content item 1: image_url
        self.assertEqual(user_msg["content"][1]["type"], "image_url")
        self.assertTrue(user_msg["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
        # Ensure worker_system unattended policy text did NOT replace the user message
        self.assertNotIn("Unattended work: implement ONLY", str(user_msg["content"]))
