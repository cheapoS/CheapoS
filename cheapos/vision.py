"""Vision sidecar and image inspection for CheapOS."""

import base64
from pathlib import Path
from typing import Any, Dict, Optional

from .gateways import gateway_for
from .providers import ChatProvider, ProviderError
from .uploads import detect_mime_type, sanitize_filename


MAX_IMAGE_SIZE_BYTES = 20 * 1024 * 1024


def resolve_image_path(task: Dict[str, Any], path_str: str, store_root: Path) -> Optional[Path]:
    """Safely resolve an image path from workspace or upload store, preventing path traversal."""
    if not isinstance(path_str, str) or not path_str.strip():
        return None

    path_str = path_str.strip()
    store_uploads = (Path(store_root).resolve() / "uploads").resolve()
    ws_root = Path(task.get("workspace", "")).resolve() if task.get("workspace") else None

    # Check against attachments in task
    for att in task.get("attachments", []):
        if not isinstance(att, dict):
            continue
        if path_str in {att.get("filename"), att.get("id"), att.get("path")}:
            if att.get("path"):
                cand = Path(att["path"]).resolve()
                if cand.is_file() and str(cand).startswith(str(store_uploads)):
                    return cand

    # Check if path is an absolute path within store uploads
    try:
        cand = Path(path_str).resolve()
        if cand.is_file() and str(cand).startswith(str(store_uploads)):
            return cand
    except Exception:
        pass

    # Check if path is relative to workspace
    if ws_root and ws_root.is_dir():
        try:
            cand = (ws_root / path_str).resolve()
            if cand.is_file() and str(cand).startswith(str(ws_root)):
                return cand
        except Exception:
            pass

    return None


def inspect_image_tool(engine: Any, task: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute inspect_image tool call for the worker or reviewer."""
    path_arg = args.get("path", "")
    query = args.get("query") or "Describe this image in detail, including layout, components, text, styling, and any visible defects or errors."

    image_path = resolve_image_path(task, path_arg, engine.store.root)
    if not image_path or not image_path.is_file():
        return {"error": f"Image file not found or inaccessible: {path_arg}"}

    try:
        data = image_path.read_bytes()
    except Exception as err:
        return {"error": f"Failed to read image file: {err}"}

    if len(data) == 0:
        return {"error": "Image file is empty"}
    if len(data) > MAX_IMAGE_SIZE_BYTES:
        return {"error": f"Image file exceeds maximum limit of {MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB"}

    mime = detect_mime_type(image_path.name, data)
    if not (mime.startswith("image/") or image_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".bmp"}):
        return {"error": f"File is not a supported image format ({mime}): {image_path.name}"}

    # Handle SVG files as text/vector markup
    if mime == "image/svg+xml" or image_path.suffix.lower() == ".svg":
        svg_text = data.decode("utf-8", errors="replace")[:12000]
        return {
            "image": image_path.name,
            "mime_type": mime,
            "size_bytes": len(data),
            "format": "svg",
            "analysis": f"SVG Vector Graphics ({len(data)} bytes):\n```xml\n{svg_text}\n```",
            "query": query,
            "status": "success",
        }

    # Prepare multimodal payload for vision model
    b64 = base64.b64encode(data).decode("ascii")
    data_uri = f"data:{mime};base64,{b64}"

    # Check if a model/provider is available
    role = task.get("active_role", "worker")
    config = (task.get("providers") or {}).get(role) or (task.get("providers") or {}).get("worker")

    if task.get("demo") or not config or engine.provider_factory is not None:
        # Scripted or mock provider environment
        return {
            "image": image_path.name,
            "mime_type": mime,
            "size_bytes": len(data),
            "analysis": f"Visual inspection of {image_path.name} ({mime}, {len(data)} bytes). Query: '{query}'. [Simulated vision response in demo/test environment]",
            "query": query,
            "status": "mock",
        }

    try:
        provider = gateway_for(engine.gateway_config(config), engine.provider_key(role, config))
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"You are a software engineering vision assistant inspecting a visual artifact. Answer this query specifically: {query}"},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ]
        res = provider.complete_brief(messages, [], 1024, None, lambda: False)
        content = res.get("content", "")
        return {
            "image": image_path.name,
            "mime_type": mime,
            "size_bytes": len(data),
            "analysis": content.strip() if content else "Vision model returned an empty response.",
            "query": query,
            "status": "success",
        }
    except Exception as err:
        return {
            "image": image_path.name,
            "mime_type": mime,
            "size_bytes": len(data),
            "analysis": f"[Image loaded ({mime}, {len(data)} bytes). Vision model inspection unavailable: {err}]",
            "query": query,
            "status": "fallback",
        }
