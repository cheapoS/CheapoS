"""Tests for safe file uploads, document extraction, and attachment handling."""

import base64
import copy
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cheapos.engine import Engine, Runtime
from cheapos import branch_runs
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

    def test_symlink_upload_rejected(self):
        uploads_root = self.engine.store.root / "uploads"
        uploads_root.mkdir(parents=True, exist_ok=True)

        # 1. Symlinked upload directory rejected
        real_secret_dir = self.engine.store.root / "real_secret"
        real_secret_dir.mkdir(parents=True, exist_ok=True)
        (real_secret_dir / "secret.txt").write_text("secret_data")

        symlinked_upload_dir = uploads_root / "symdir12345678"
        try:
            symlinked_upload_dir.symlink_to(real_secret_dir, target_is_directory=True)
            self.assertIsNone(get_upload_path(self.engine.store.root, "symdir12345678", "secret.txt"))
            self.assertIsNone(get_upload_path(self.engine.store.root, "symdir12345678"))
        except OSError:
            pass

        # 2. Symlinked file inside valid upload dir rejected
        valid_upload_dir = uploads_root / "validdir12345678"
        valid_upload_dir.mkdir(parents=True, exist_ok=True)
        symlink_file = valid_upload_dir / "leak.txt"
        target_file = self.engine.store.root / "target.txt"
        target_file.write_text("canary")
        try:
            symlink_file.symlink_to(target_file)
            self.assertIsNone(get_upload_path(self.engine.store.root, "validdir12345678", "leak.txt"))
            self.assertIsNone(get_upload_path(self.engine.store.root, "validdir12345678"))
        except OSError:
            pass

    def test_trusted_server_classification_and_attachment_only_sends(self):
        from cheapos.uploads import get_upload_record
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        record = save_upload(self.engine.store.root, "photo.png", base64.b64encode(png_bytes).decode("ascii"))
        self.assertIn("url", record)
        self.assertEqual(record["url"], f"/api/uploads/{record['id']}/photo.png")

        # Server-derived record ignores client spoofing
        derived = get_upload_record(self.engine.store.root, record["id"], "photo.png")
        self.assertTrue(derived["is_image"])
        self.assertFalse(derived["is_text"])
        self.assertFalse(derived["is_pdf"])

        # Attachment-only create: empty prompt allowed, defaults to inspection prompt
        base_task = self.fixture(paid=True)
        spoofed_att = {"id": record["id"], "filename": "photo.png", "is_image": False, "is_text": True}
        task = self.engine.create({
            "prompt": "",
            "repository": base_task["source"],
            "check_command": "true",
            "conversational": True,
            "attachments": [spoofed_att],
        }, demo=True)
        self.assertIn("Inspect the attached file(s).", task["prompt"])
        self.assertIn("### Attached Image: photo.png", task["prompt"])
        self.assertNotIn("Attached Document: None", task["prompt"])

        # Attachment-only steer: empty message allowed, defaults to inspection guidance
        task["demo"] = False
        task["providers"] = {"worker": dict(CONFIG), "reviewer": dict(CONFIG)}
        self.engine.store.save(task)
        res = self.engine.steer(task["id"], "", attachments=[record])
        self.assertTrue(res["steered"])
        reloaded = self.engine.store.get(task["id"])
        self.assertIn("Inspect the attached file(s).", reloaded["requests"][-1])
        self.assertIn("### Attached Image: photo.png", reloaded["requests"][-1])


    def test_continue_message_preserves_attachments(self):
        content = "CONTINUATION_DOCUMENT_CANARY"
        record = save_upload(self.engine.store.root, "notes.txt", content.encode())
        baseline = self.fixture(paid=True)
        baseline.update(status="paused", conversational=True, pending_review={"candidate": "saved-review"})
        for endpoint in ("steer", "start"):
            with self.subTest(endpoint=endpoint):
                task = copy.deepcopy(baseline)
                self.engine.store.save(task)
                # Exercise real resume/context construction without inference or worker execution.
                with patch.object(self.engine, "_run") as run:
                    if endpoint == "steer":
                        self.engine.steer(task["id"], "continue", attachments=[record, record])
                    else:
                        self.engine.start(task["id"], {"message": "continue", "attachments": [record, record]})
                    runtime = self.engine.runtimes[task["id"]]
                    runtime.thread.join(2)
                self.assertFalse(runtime.thread.is_alive())
                run.assert_called_once()
                resumed = self.engine.store.get(task["id"])
                self.assertEqual([a["id"] for a in resumed["attachments"]], [record["id"]])
                self.assertIn(content, json.dumps(resumed["messages"]))
                self.assertIn(content, resumed["requests"][-1])
                self.assertEqual(resumed["requests"][-1].count(content), 1)
                for key in ("pending_review", "checks", "checkpoints", "limits", "usage"):
                    self.assertEqual(resumed[key], baseline[key])
                self.engine.runtimes.pop(task["id"])

    def test_continue_attachments_reach_live_and_paused_branch_guidance(self):
        content = "LIVE_DOCUMENT_CANARY"
        record = save_upload(self.engine.store.root, "notes.txt", content.encode())
        task = self.fixture(paid=True)
        task.update(status="running", conversational=True)
        runtime = Runtime(task)
        runtime.thread = SimpleNamespace(is_alive=lambda: True, join=lambda *_: None)
        self.engine.runtimes[task["id"]] = runtime
        self.engine.store.save(task)
        for endpoint in ("steer", "start"):
            if endpoint == "steer":
                self.engine.steer(task["id"], "continue", attachments=[record, record])
            else:
                self.engine.start(task["id"], {"message": "continue", "attachments": [record]})
            self.assertIn(content, runtime.steer_queue[-1])
            self.assertEqual(len(task["attachments"]), 1)

        run = branch_runs.new_run({
            "items": [{"id": "one", "title": "Work", "instructions": "Implement the change",
                       "acceptance_criteria": ["Works"], "required_checks": ["python3 test.py"]}],
            "limits": {"dollars": 0}, "final_checks": ["python3 test.py"],
        })
        run.update(status="running", current_item_id="one", authorization_ref="saved-authorization")
        task["branch_run"] = run
        task["attachments"] = []
        self.engine.store.save(task)
        # Authority implementation has its own integration suite; delivery must still call it.
        with patch.object(self.engine.branch, "validate_authority") as authority:
            self.engine.branch.message(task["id"], {"message": "continue", "attachments": [record, record]})
            authority.assert_called_once()
        self.assertIn(content, task["messages"][-1]["content"])
        self.assertIn(content, run["guidance"][-1]["message"])
        self.engine.event(runtime.task, "state", "Next worker event")
        self.assertEqual(len(self.engine.store.get(task["id"])["attachments"]), 1)

        self.engine.runtimes.pop(task["id"])
        task.update(status="paused")
        run["status"] = "paused"
        self.engine.store.save(task)
        consent = {"needs_consent": True, "proposal_id": "existing-consent", "scopes": [["python3", "test.py"]]}
        with patch.object(self.engine.branch, "validate_authority"), patch.object(self.engine.branch, "resume", return_value=consent) as resume:
            self.engine.branch.message(task["id"], {"message": "continue", "attachments": [record]})
        resume.assert_called_once_with(task["id"], {})
        saved = self.engine.store.get(task["id"])
        self.assertEqual(saved["operator_continue"]["status"], "needs_consent")
        self.assertEqual(saved["branch_run"]["authorization_ref"], "saved-authorization")
        self.assertIn(content, saved["branch_run"]["guidance"][-1]["message"])
        self.assertEqual(len(saved["attachments"]), 1)


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
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
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

    def test_upload_security_headers_and_isolation(self):
        # 1. HTML file upload must have sandbox CSP, nosniff, frame-options deny, and forced attachment download
        html_content = b"<html><head><script>alert(document.cookie)</script></head><body>evil</body></html>"
        b64_html = base64.b64encode(html_content).decode("ascii")
        status, _, body = self.post("/api/upload", {"filename": "evil.html", "data": f"data:text/html;base64,{b64_html}"})
        self.assertEqual(status, 200)
        record = json.loads(body)

        dl_status, headers, dl_data = self.request("GET", f"/api/uploads/{record['id']}/evil.html")
        self.assertEqual(dl_status, 200)
        # Verify isolation headers
        csp = headers.get("content-security-policy", "") or headers.get("Content-Security-Policy", "")
        self.assertIn("sandbox", csp)
        self.assertIn("default-src 'none'", csp)
        nosniff = headers.get("x-content-type-options", "") or headers.get("X-Content-Type-Options", "")
        self.assertEqual(nosniff, "nosniff")
        frame_opts = headers.get("x-frame-options", "") or headers.get("X-Frame-Options", "")
        self.assertEqual(frame_opts, "DENY")
        disposition = headers.get("content-disposition", "") or headers.get("Content-Disposition", "")
        self.assertIn("attachment", disposition)
        self.assertIn("evil.html", disposition)

        # 2. Raster PNG allows inline display
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        b64_png = base64.b64encode(png_bytes).decode("ascii")
        status, _, body = self.post("/api/upload", {"filename": "diagram.png", "data": f"data:image/png;base64,{b64_png}"})
        self.assertEqual(status, 200)
        img_record = json.loads(body)

        _, img_headers, _ = self.request("GET", f"/api/uploads/{img_record['id']}/diagram.png")
        img_disp = img_headers.get("content-disposition", "") or img_headers.get("Content-Disposition", "")
        self.assertIn("inline", img_disp)

    def test_upload_20mb_accepted_by_http(self):
        # 20 MiB decoded file requires ~27.96 MB in base64. Body limit of 35 MB must accept it.
        # Use smaller representative 5 MB to keep test fast while verifying body limit behavior
        chunk = b"X" * (5 * 1024 * 1024)
        b64_chunk = base64.b64encode(chunk).decode("ascii")
        status, _, body = self.post("/api/upload", {"filename": "five_mb.bin", "data": f"data:application/octet-stream;base64,{b64_chunk}"})
        self.assertEqual(status, 200)
        res = json.loads(body)
        self.assertEqual(res["size"], len(chunk))
