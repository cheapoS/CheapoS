"""Tests for vision sidecar and inspect_image tool execution."""

import base64
from pathlib import Path

from cheapos.uploads import save_upload
from cheapos.vision import inspect_image_tool, resolve_image_path
from test_engine import LocalCase


class VisionToolTests(LocalCase):
    def test_resolve_image_path(self):
        ws_dir = self.engine.store.root / "mock_workspace"
        ws_dir.mkdir(parents=True, exist_ok=True)
        img_file = ws_dir / "diagram.png"
        img_file.write_bytes(b"\x89PNG\r\n\x1a\n")

        task = {"workspace": str(ws_dir), "attachments": []}
        # Resolve workspace relative
        resolved = resolve_image_path(task, "diagram.png", self.engine.store.root)
        self.assertEqual(resolved, img_file)

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
