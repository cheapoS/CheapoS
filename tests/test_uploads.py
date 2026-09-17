"""Tests for safe file uploads, document extraction, and attachment handling."""

import base64
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from cheapos.engine import Engine
from cheapos.server import LocalServer
from cheapos.uploads import (
    MAX_FILE_SIZE_BYTES,
    detect_mime_type,
    extract_document_text,
    get_upload_path,
    sanitize_filename,
    save_upload,
)
from test_engine import CONFIG, LocalCase


class UploadStorageTests(LocalCase):
    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("../../../etc/passwd"), "passwd")
        self.assertEqual(sanitize_filename("image..png"), "image.png")
        self.assertEqual(sanitize_filename("my file (1).png"), "my_file__1_.png")
        self.assertTrue(sanitize_filename("").startswith("unnamed_file"))

    def test_detect_mime_type(self):
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        self.assertEqual(detect_mime_type("photo.png", png_bytes), "image/png")
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        self.assertEqual(detect_mime_type("photo.jpg", jpeg_bytes), "image/jpeg")
        pdf_bytes = b"%PDF-1.4\n%..."
        self.assertEqual(detect_mime_type("doc.pdf", pdf_bytes), "application/pdf")
        svg_bytes = b"<svg xmlns='http://www.w3.org/2000/svg'><circle/></svg>"
        self.assertEqual(detect_mime_type("icon.svg", svg_bytes), "image/svg+xml")
        txt_bytes = b"Hello world"
        self.assertEqual(detect_mime_type("notes.txt", txt_bytes), "text/plain")

    def test_save_upload_and_retrieval(self):
        content = b"Sample text document for upload testing"
        encoded = base64.b64encode(content).decode("ascii")
        record = save_upload(self.engine.store.root, "notes.txt", encoded)
        self.assertEqual(record["filename"], "notes.txt")
        self.assertEqual(record["size"], len(content))
        self.assertTrue(record["is_text"])
        self.assertFalse(record["is_image"])

        # Retrieve safely
        resolved = get_upload_path(self.engine.store.root, record["id"], "notes.txt")
        self.assertIsNotNone(resolved)
        self.assertTrue(resolved.is_file())
        self.assertEqual(resolved.read_bytes(), content)

        # Path traversal rejected
        self.assertIsNone(get_upload_path(self.engine.store.root, "../../../etc", "passwd"))
        self.assertIsNone(get_upload_path(self.engine.store.root, record["id"], "../../../etc/passwd"))

    def test_save_upload_rejects_empty_and_oversized(self):
        with self.assertRaises(ValueError):
            save_upload(self.engine.store.root, "empty.txt", "")
        oversized = base64.b64encode(b"X" * (MAX_FILE_SIZE_BYTES + 1024)).decode("ascii")
        with self.assertRaises(ValueError):
            save_upload(self.engine.store.root, "big.bin", oversized)

    def test_extract_document_text(self):
        sample_file = self.engine.store.root / "sample.py"
        sample_file.write_text("def hello():\n    return 42\n", encoding="utf-8")
        text = extract_document_text(sample_file)
        self.assertIn("def hello():", text)

        # Truncation if excessive
        large_file = self.engine.store.root / "large.txt"
        large_file.write_text("A" * 25000, encoding="utf-8")
        text_truncated = extract_document_text(large_file)
        self.assertIn("Content truncated", text_truncated)

    def test_task_creation_and_messaging_with_attachments(self):
        base_task = self.fixture(paid=True)
        content = b"def calculate(): return 100\n"
        record = save_upload(self.engine.store.root, "calc.py", base64.b64encode(content).decode("ascii"))

        task = self.engine.create({
            "prompt": "Inspect the attached calculation module",
            "repository": base_task["source"],
            "check_command": "true",
            "conversational": True,
            "attachments": [record],
        }, demo=True)
        self.assertEqual(len(task["attachments"]), 1)
        self.assertIn("### Attached Document: calc.py", task["prompt"])
        self.assertIn("def calculate():", task["prompt"])

        # Followup message with attachment
        img_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        img_record = save_upload(self.engine.store.root, "screen.png", base64.b64encode(img_bytes).decode("ascii"))
        task["demo"] = False
        task["providers"] = {"worker": dict(CONFIG), "reviewer": dict(CONFIG)}
        self.engine.store.save(task)
        self.engine.provider_factory = lambda role, config: None

        self.engine.start(task["id"], {
            "message": "Here is the screenshot",
            "attachments": [img_record],
        })
        reloaded = self.engine.store.get(task["id"])
        self.assertEqual(len(reloaded["attachments"]), 2)
        self.assertIn("### Attached Image: screen.png", reloaded["requests"][-1])


class UploadHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = Engine(Path(self.temp.name) / "state", fixture_delay=0)
        self.server = LocalServer(("127.0.0.1", 0), Path(__file__).resolve().parent.parent / "dist", self.engine)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.engine.shutdown()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        conn.request(method, path, json.dumps(body) if body is not None else None, headers or {})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def post(self, path, body):
        return self.request("POST", path, body, {"Content-Type": "application/json", "X-CheapOS-Token": self.server.token})

    def test_upload_api_and_download(self):
        content = b"Image or document binary content"
        b64 = base64.b64encode(content).decode("ascii")
        status, _, body = self.post("/api/upload", {"filename": "data.txt", "data": f"data:text/plain;base64,{b64}"})
        self.assertEqual(status, 200)
        record = json.loads(body)
        self.assertIn("id", record)
        self.assertEqual(record["filename"], "data.txt")

        # Download via GET /api/uploads/<id>/<filename>
        dl_status, _, dl_data = self.request("GET", f"/api/uploads/{record['id']}/data.txt")
        self.assertEqual(dl_status, 200)
        actual = dl_data.encode("utf-8") if isinstance(dl_data, str) else dl_data
        self.assertEqual(actual, content)

        # Missing file returns 404
        missing_status, _, _ = self.request("GET", f"/api/uploads/{record['id']}/nonexistent.txt")
        self.assertEqual(missing_status, 404)
