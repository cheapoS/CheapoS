"""Vision sidecar and image inspection for CheapOS."""

import base64
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

from .gateways import gateway_for
from .providers import ChatProvider, ProviderError, BudgetError
from .uploads import detect_mime_type, sanitize_filename


MAX_IMAGE_SIZE_BYTES = 20 * 1024 * 1024


def resolve_image_path(task: Dict[str, Any], path_str: str, store_root: Path) -> Optional[Path]:
    """Safely resolve an image path from workspace or upload store, preventing path traversal and symlink escapes."""
    if not isinstance(path_str, str) or not path_str.strip():
        return None

    from .uploads import get_upload_path
    path_str = path_str.strip()
    store_uploads = (Path(store_root).resolve() / "uploads").resolve()
    ws_root = Path(task.get("workspace", "")).resolve() if task.get("workspace") else None

    # Check against attachments in task
    for att in task.get("attachments", []):
        if not isinstance(att, dict):
            continue
        upload_id = att.get("id")
        filename = att.get("filename") or att.get("name")
        if upload_id and path_str in {filename, upload_id, att.get("path")}:
            cand = get_upload_path(store_root, upload_id, filename)
            if cand and cand.is_file():
                return cand

    # Check if path is an absolute path within store uploads
    try:
        cand = Path(path_str)
        curr = cand
        while curr != store_uploads and curr.parent != curr:
            if curr.is_symlink():
                return None
            curr = curr.parent
        resolved = cand.resolve()
        if resolved.is_file() and resolved.is_relative_to(store_uploads):
            return resolved
    except (ValueError, OSError):
        pass

    # Check if path is relative to workspace
    if ws_root and ws_root.is_dir():
        try:
            target = ws_root / path_str
            curr = target
            while curr != ws_root and curr.parent != curr:
                if curr.is_symlink():
                    return None
                curr = curr.parent
            resolved = target.resolve()
            if resolved.is_file() and resolved.is_relative_to(ws_root):
                return resolved
        except (ValueError, OSError):
            pass

    return None


def inspect_image_tool(engine: Any, task: Dict[str, Any], args: Dict[str, Any], runtime: Optional[Any] = None, *, role: Optional[str] = None) -> Dict[str, Any]:
    """Execute inspect_image tool call for the worker or reviewer, properly metered and accounted."""
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

    # Handle SVG files as text/vector markup directly without model tokens
    if mime == "image/svg+xml" or image_path.suffix.lower() == ".svg":
        svg_text = data.decode("utf-8", errors="replace")[:12000]
        return {
            "image": image_path.name,
            "mime_type": mime,
            "size_bytes": len(data),
            "format": "svg",
            "image_digest": hashlib.sha256(data).hexdigest(),
            "analysis": f"SVG Vector Graphics ({len(data)} bytes):\n```xml\n{svg_text}\n```",
            "query": query,
            "status": "success",
        }

    # Prepare multimodal payload for vision model
    b64 = base64.b64encode(data).decode("ascii")
    data_uri = f"data:{mime};base64,{b64}"

    # Check if a model/provider is available
    role = role or ("reviewer" if task.get("status") == "reviewing" else task.get("active_role", "worker"))
    config = (task.get("providers") or {}).get(role)
    if role == 'reviewer' and not config and not task.get('demo'):
        return {'error': 'Independent reviewer is unavailable for image inspection.'}

    active_runtime = runtime
    if active_runtime is None and hasattr(engine, "runtimes"):
        active_runtime = engine.runtimes.get(task.get("id"))
    if active_runtime is None and not task.get("demo") and config:
        try:
            from .engine import Runtime
            active_runtime = Runtime(task)
        except Exception:
            active_runtime = None

    if task.get("demo") or not config:
        # Scripted or mock provider environment without active runtime
        return {
            "image": image_path.name,
            "mime_type": mime,
            "size_bytes": len(data),
            "analysis": f"Visual inspection of {image_path.name} ({mime}, {len(data)} bytes). Query: '{query}'. [Simulated vision response in demo/test environment]",
            "query": query,
            "status": "mock",
        }

    try:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"You are a software engineering vision assistant inspecting a visual artifact. Answer this query specifically: {query}"},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ]

        if active_runtime is not None and hasattr(engine, "_request"):
            # Route through controller's metered request lifecycle: reserves tokens, checks budget, reconciles usage, and supports cancellation
            res = engine._request(active_runtime, messages, tools=[], role=role, purpose="vision")
            content = res.get("content", "") if isinstance(res, dict) else str(res)
        else:
            provider = gateway_for(engine.gateway_config(config), engine.provider_key(role, config))
            cancel_fn = getattr(active_runtime, 'request_cancelled', active_runtime.stop.is_set if active_runtime else (lambda: False))
            res = provider.complete_brief(messages, [], 1024, None, cancel_fn)
            content = res.get("content", "") if isinstance(res, dict) else str(res)

        return {
            "image": image_path.name,
            "mime_type": mime,
            "size_bytes": len(data),
            "analysis": content.strip() if content else "",
            "image_digest": hashlib.sha256(data).hexdigest(),
            "role": role,
            "query": query,
            "status": "success",
        }
    except (BudgetError, InterruptedError):
        raise
    except Exception as err:
        return {
            "image": image_path.name,
            "mime_type": mime,
            "size_bytes": len(data),
            "analysis": f"[Image loaded ({mime}, {len(data)} bytes). Vision model inspection unavailable: {err}]",
            "query": query,
            "status": "fallback",
        }
