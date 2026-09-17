"""Secure file upload storage, MIME classification, and document extraction."""

import base64
import binascii
import mimetypes
import os
import re
import uuid
from pathlib import Path, PurePath
from typing import Any, Dict, Optional

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB per file
MAX_TOTAL_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_DOC_CHARS = 20000

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp"}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".json", ".csv", ".tsv", ".yaml", ".yml",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss",
    ".sh", ".bash", ".zsh", ".sql", ".xml", ".ini", ".toml", ".env"
}


def sanitize_filename(filename: str) -> str:
    """Sanitize a user-provided filename to prevent path traversal and unsafe characters."""
    if not isinstance(filename, str) or not filename.strip():
        return "unnamed_file"
    base = PurePath(filename.strip()).name
    # Strip dangerous characters, keep alphanumerics, dots, dashes, underscores
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
    cleaned = re.sub(r"\.{2,}", ".", cleaned)  # prevent ..
    if not cleaned.strip("._-"):
        return f"file_{uuid.uuid4().hex[:8]}"
    return cleaned[:120]


def detect_mime_type(filename: str, data: bytes) -> str:
    """Detect MIME type from file extension and magic byte signatures."""
    ext = Path(filename).suffix.lower()

    # Magic byte signatures
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if ext == ".svg" or (b"<svg" in data[:1000].lower() and b"</svg>" in data.lower()):
        return "image/svg+xml"

    # Extension-based mapping
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        return guessed
    if ext in TEXT_EXTENSIONS:
        return "text/plain"
    return "application/octet-stream"


def decode_upload_data(raw_data: Any) -> bytes:
    """Decode raw upload payload from base64 string, data URI, or bytes."""
    if isinstance(raw_data, bytes):
        return raw_data
    if not isinstance(raw_data, str):
        raise ValueError("Upload payload must be a string or bytes")

    # Handle data URLs: data:<mime>;base64,<encoded>
    if "," in raw_data and raw_data.strip().startswith("data:"):
        _, encoded = raw_data.split(",", 1)
    else:
        encoded = raw_data.strip()

    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as err:
        raise ValueError(f"Invalid base64 encoding: {err}") from err


def save_upload(
    store_root: Path,
    filename: str,
    raw_data: Any,
    mime_type: Optional[str] = None
) -> Dict[str, Any]:
    """Store an uploaded file into the private uploads directory and return its metadata."""
    data = decode_upload_data(raw_data)
    if len(data) == 0:
        raise ValueError("Upload file cannot be empty")
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File exceeds maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB")

    safe_name = sanitize_filename(filename)
    detected_mime = mime_type or detect_mime_type(safe_name, data)
    upload_id = uuid.uuid4().hex[:16]

    upload_dir = Path(store_root).resolve() / "uploads" / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    target_path = upload_dir / safe_name
    fd = os.open(str(target_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)

    is_image = detected_mime.startswith("image/") or Path(safe_name).suffix.lower() in IMAGE_EXTENSIONS
    is_pdf = detected_mime == "application/pdf" or Path(safe_name).suffix.lower() == ".pdf"
    is_text = detected_mime.startswith("text/") or Path(safe_name).suffix.lower() in TEXT_EXTENSIONS

    return {
        "id": upload_id,
        "filename": safe_name,
        "path": str(target_path),
        "mime_type": detected_mime,
        "size": len(data),
        "is_image": is_image,
        "is_pdf": is_pdf,
        "is_text": is_text,
    }


def get_upload_path(store_root: Path, upload_id: str, filename: Optional[str] = None) -> Optional[Path]:
    """Resolve an uploaded file path safely, rejecting path traversal."""
    if not isinstance(upload_id, str) or not re.match(r"^[a-zA-Z0-9_-]{8,64}$", upload_id):
        return None
    upload_dir = (Path(store_root).resolve() / "uploads" / upload_id).resolve()
    if not upload_dir.exists() or not upload_dir.is_dir():
        return None
    if filename:
        safe_name = sanitize_filename(filename)
        candidate = (upload_dir / safe_name).resolve()
        if candidate.is_file() and str(candidate).startswith(str(upload_dir)):
            return candidate
        return None
    # Return first file in upload_dir if no filename given
    files = [f for f in upload_dir.iterdir() if f.is_file()]
    return files[0] if files else None


def extract_document_text(file_path: Path, max_chars: int = MAX_DOC_CHARS) -> str:
    """Extract plain text from uploaded documents (text, markdown, JSON, code, or PDF)."""
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return ""

    ext = path.suffix.lower()
    if ext == ".pdf":
        return _extract_pdf_text(path, max_chars=max_chars)

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n... [Content truncated at {max_chars} characters]"
        return content
    except Exception as e:
        return f"[Error reading document: {e}]"


def _extract_pdf_text(path: Path, max_chars: int = MAX_DOC_CHARS) -> str:
    """Lightweight text extraction from PDF files."""
    try:
        raw_bytes = path.read_bytes()
        text_parts = []
        for match in re.finditer(rb"BT\s*(.*?)\s*ET", raw_bytes, re.DOTALL):
            chunk = match.group(1)
            for str_match in re.finditer(rb"\((.*?)\)\s*Tj", chunk):
                try:
                    text_parts.append(str_match.group(1).decode("utf-8", errors="ignore"))
                except Exception:
                    continue
        extracted = " ".join(text_parts).strip()
        if extracted:
            if len(extracted) > max_chars:
                extracted = extracted[:max_chars] + f"\n\n... [Content truncated at {max_chars} characters]"
            return extracted
        return f"[PDF document: {path.name} ({len(raw_bytes)} bytes)]"
    except Exception as e:
        return f"[PDF document: {path.name} (Error extracting text: {e})]"
