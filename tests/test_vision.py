"""Tests for vision sidecar and inspect_image tool execution."""

import base64
from pathlib import Path

from cheapos.uploads import save_upload
from cheapos.vision import inspect_image_tool, resolve_image_path
from test_engine import LocalCase


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
