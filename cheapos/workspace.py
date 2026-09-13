"""Repository snapshots and constrained file tools. Check commands are NOT OS-sandboxed."""

import codecs
import hashlib
import math
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path, PurePosixPath


MAX_FILE_BYTES = 256_000
MAX_EDIT_BYTES = 3000
MAX_EDIT_LINES = 80
MAX_SNAPSHOT_BYTES = 100_000_000
MAX_FILES = 5000
BLOCKED_PARTS = {".git", ".cheapos", ".ssh", ".aws", ".gnupg", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
BLOCKED_NAMES = {".env", ".npmrc", ".pypirc", ".netrc", "id_rsa", "id_ed25519", "credentials", "credentials.json"}


class FileVersionError(ValueError):
    """The edit's inspected version does not match the file on disk."""


def allowed_name(name):
    parts = PurePosixPath(name).parts
    return bool(parts) and not any(p in BLOCKED_PARTS or p in BLOCKED_NAMES or (p.startswith(".env.") and p not in {".env.example", ".env.sample", ".env.template"}) or p.endswith((".pem", ".key", ".p12", ".pfx")) for p in parts)


def git(directory, *args, binary=False):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"})
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgSign=false", "-c", "core.fsmonitor=false", *args],
        cwd=str(directory), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace")[:1000].strip() or "Git command failed")
    return result.stdout if binary else result.stdout.decode("utf-8", errors="replace")


class Workspace:
    def __init__(self, directory):
        self.root = Path(directory).resolve()

    @staticmethod
    def project_root(source):
        if not isinstance(source, (str, Path)) or not str(source).strip():
            raise ValueError("Choose a local Git repository directory")
        source = Path(source).expanduser().resolve(strict=True)
        if not source.is_dir():
            raise ValueError("Choose a local Git repository directory")
        top = Path(git(source, "rev-parse", "--show-toplevel").strip()).resolve()
        if top != source:
            raise ValueError("Choose the root of the Git repository: " + str(top))
        return source

    @classmethod
    def snapshot(cls, source, destination):
        source = cls.project_root(source)
        destination = Path(destination).resolve()
        if destination == source or destination in source.parents:
            raise ValueError("Snapshot destination must not contain the source repository")
        names = git(source, "ls-files", "--cached", "--others", "--exclude-standard", "-z", binary=True).decode("utf-8").split("\0")
        selected, skipped, size = [], [], 0
        for name in sorted(set(filter(None, names))):
            candidate = source / name
            if not allowed_name(name) or candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents if parent != source):
                skipped.append(name)
                continue
            if not candidate.is_file():
                continue
            resolved = candidate.resolve()
            if source not in resolved.parents or destination == resolved or destination in resolved.parents:
                skipped.append(name)
                continue
            data = candidate.read_bytes()
            if len(data) > 2_000_000:
                skipped.append(name)
                continue
            size += len(data)
            if size > MAX_SNAPSHOT_BYTES or len(selected) >= MAX_FILES:
                raise ValueError("Repository snapshot is too large (limit: 5,000 files / 100 MB)")
            selected.append((name, data, candidate.stat().st_mode))
        if not selected:
            raise ValueError("No eligible files found in this repository")
        destination.mkdir(parents=True, mode=0o700)
        for name, data, mode in selected:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(0o700 if mode & 0o111 else 0o600)
        git(destination, "init", "-q")
        git(destination, "add", "-f", "--", *[n for n, _, _ in selected])
        git(destination, "-c", "user.name=cheapoS", "-c", "user.email=local@cheapos.invalid", "commit", "-qm", "Local task baseline")
        return cls(destination), {"files": len(selected), "skipped": skipped, "source": str(source)}

    def path(self, name):
        if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
            raise ValueError("Provide a relative file path")
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or not allowed_name(name):
            raise ValueError("Path is outside the allowed workspace files")
        target = self.root / name
        current = target
        while current != self.root:
            if current.is_symlink():
                raise ValueError("Symlinks cannot be used by file tools")
            current = current.parent
        resolved = target.resolve()
        if self.root not in resolved.parents:
            raise ValueError("Path is outside the workspace")
        return target

    def list_files(self, path="."):
        if not isinstance(path, str) or not path or "\x00" in path or "\\" in path:
            raise ValueError("Provide a relative directory path, or '.' for the whole project")
        target = self.root if PurePosixPath(path) == PurePosixPath(".") else self.path(path)
        if not target.is_dir():
            raise ValueError("Directory not found. Use '.' to list the project; write_file creates parent directories for new files.")
        prefix = "" if target == self.root else target.relative_to(self.root).as_posix() + "/"
        names = git(self.root, "ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")
        return sorted(n for n in set(names) if n and n.startswith(prefix) and allowed_name(n) and not (self.root / n).is_symlink())[:MAX_FILES]

    def read_file(self, path, start_line=1, end_line=200):
        data = self.text_bytes(path)
        if type(start_line) is not int or type(end_line) is not int or start_line < 1 or end_line < start_line:
            raise ValueError("Invalid line range")
        lines = data.decode("utf-8").splitlines()
        end_line = min(end_line, start_line + 299)
        content = "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines) if start_line - 1 <= i < end_line)
        return {"path": path, "total_lines": len(lines), "start_line": start_line, "end_line": min(end_line, len(lines)),
                "hash": hashlib.sha256(data).hexdigest(), "content": content[:20_000],
                "complete": start_line == 1 and end_line >= len(lines) and len(content) <= 20_000}

    def text_bytes(self, path):
        target = self.path(path)
        if not target.is_file():
            raise ValueError("File not found")
        with target.open("rb") as source:
            data = source.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("File is too large for the text tools")
        data.decode("utf-8")
        if b"\x00" in data:
            raise ValueError("Binary files cannot be read by the text tools")
        return data

    def replace_lines(self, path, start_line, end_line, new_text, expected_hash):
        """A bounded edit against the exact bytes the worker inspected."""
        data = self.text_bytes(path)
        if expected_hash != hashlib.sha256(data).hexdigest():
            raise FileVersionError("The edit version does not match the current file. No edit was made; inspect the refreshed lines before retrying.")
        lines = data.decode("utf-8").splitlines(keepends=True)
        if (type(start_line) is not int or type(end_line) is not int or start_line < 1
                or start_line > len(lines) + 1 or end_line < start_line - 1 or end_line > len(lines)):
            raise ValueError("Invalid line range. Lines are 1-based and inclusive; end_line = start_line - 1 inserts before start_line.")
        if (not isinstance(new_text, str) or len(new_text.encode("utf-8")) > MAX_EDIT_BYTES
                or len(new_text.splitlines()) > MAX_EDIT_LINES or end_line - start_line + 1 > MAX_EDIT_LINES):
            raise ValueError("Edit is too large. Replace at most 80 lines with at most 80 lines / 3000 UTF-8 bytes per call.")
        if "\x00" in new_text:
            raise ValueError("Binary content cannot be written by the text tools")
        prefix, suffix = "".join(lines[:start_line - 1]), "".join(lines[end_line:])
        newline = "\r\n" if b"\r\n" in data else "\n"
        if new_text and prefix and not prefix.endswith(("\n", "\r")):
            prefix += newline
        if new_text and suffix and not new_text.endswith(("\n", "\r")):
            new_text += newline
        replacement = (prefix + new_text + suffix).encode("utf-8")
        if len(replacement) > MAX_FILE_BYTES:
            raise ValueError("Replacement is too large")
        self.path(path).write_bytes(replacement)
        result = {"path": path, "updated": True, "hash": hashlib.sha256(replacement).hexdigest(),
                  "total_lines": len(replacement.decode("utf-8").splitlines())}
        warning = self.validate_syntax(path)
        if warning:
            result["syntax_warning"] = warning
        return result

    def validate_syntax(self, path):
        """Fast syntax check for edited files. Returns an error description or None."""
        try:
            target = self.path(path)
            if not target.is_file():
                return None
            data = target.read_bytes()
            if path.endswith(".py"):
                import ast
                ast.parse(data, filename=path)
            elif path.endswith(".json"):
                import json
                json.loads(data.decode("utf-8"))
        except SyntaxError as err:
            return f"SyntaxError at line {err.lineno}: {err.msg}"
        except ValueError as err:
            return f"FormatError: {err}"
        except Exception:
            return None
        return None

    def outline_file(self, path):
        """Return the class, method, and function outlines with line numbers for a file."""
        data = self.text_bytes(path)
        text = data.decode("utf-8")
        if path.endswith(".py"):
            import ast
            try:
                tree = ast.parse(data, filename=path)
            except SyntaxError as err:
                return {"path": path, "outline": f"SyntaxError at line {err.lineno}: {err.msg}", "total_lines": len(text.splitlines())}
            outline = []
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    end = getattr(node, "end_lineno", node.lineno)
                    args = [a.arg for a in node.args.args]
                    outline.append(f"def {node.name}({', '.join(args)}) (lines {node.lineno}–{end})")
                elif isinstance(node, ast.ClassDef):
                    end = getattr(node, "end_lineno", node.lineno)
                    outline.append(f"class {node.name} (lines {node.lineno}–{end})")
                    for sub in node.body:
                        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            sub_end = getattr(sub, "end_lineno", sub.lineno)
                            sub_args = [a.arg for a in sub.args.args]
                            outline.append(f"  def {sub.name}({', '.join(sub_args)}) (lines {sub.lineno}–{sub_end})")
            if not outline:
                return {"path": path, "outline": "(No top-level functions or classes found)", "total_lines": len(text.splitlines())}
            return {"path": path, "outline": "\n".join(outline), "total_lines": len(text.splitlines())}
        else:
            outline = []
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith(("#", "function ", "class ", "export function ", "export class ", "def ")):
                    outline.append(f"line {i}: {stripped[:100]}")
                    if len(outline) >= 100:
                        break
            return {"path": path, "outline": "\n".join(outline) if outline else "(No outline symbols found)", "total_lines": len(text.splitlines())}

    def search(self, query):
        if not isinstance(query, str) or not query or len(query) > 200:
            raise ValueError("Search query must contain 1–200 characters")
        matches = []
        for name in self.list_files():
            try:
                target = self.path(name)
                if target.stat().st_size > MAX_FILE_BYTES:
                    continue
                for line_number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
                    if query.casefold() in line.casefold():
                        matches.append({"path": name, "line": line_number, "text": line[:300]})
                        if len(matches) >= 60:
                            return matches
            except (OSError, UnicodeError, ValueError):
                continue
        return matches

    def write_file(self, path, content):
        if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError("Content must be text under 256 KB")
        target = self.path(path)
        if target.exists():
            raise ValueError("File already exists; use an offered replacement tool for existing files")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        target.chmod(0o600)
        result = {"path": path, "created": True}
        warning = self.validate_syntax(path)
        if warning:
            result["syntax_warning"] = warning
        return result

    def replace_text(self, path, old_text, new_text):
        target = self.path(path)
        if not isinstance(old_text, str) or not old_text or not isinstance(new_text, str):
            raise ValueError("Provide a nonempty exact old_text and a new_text string")
        if target.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("File is too large")
        text = target.read_text(encoding="utf-8")
        if text.count(old_text) != 1:
            raise ValueError("old_text must match exactly once; read the current file before editing")
        replacement = text.replace(old_text, new_text, 1)
        if len(replacement.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError("Replacement is too large")
        target.write_text(replacement, encoding="utf-8")
        result = {"path": path, "updated": True}
        warning = self.validate_syntax(path)
        if warning:
            result["syntax_warning"] = warning
        return result

    def changes(self):
        # Include newly created files in the exported patch without changing the baseline.
        names = self.list_files()
        for name in names:
            target = self.path(name)
            if target.is_file() and target.stat().st_size > 2_000_000:
                raise ValueError("Changed file exceeds the 2 MB limit: " + name)
        if names:
            git(self.root, "add", "-A", "--", *names)
        names = git(self.root, "diff", "--cached", "--name-only", "-z", "HEAD").split("\0")
        result = []
        for name in filter(None, names):
            if not allowed_name(name):
                continue
            target = self.path(name)
            try:
                before = git(self.root, "show", "HEAD:" + name, binary=True).decode("utf-8")
            except ValueError:
                before = ""
            except UnicodeError:
                before = None
            try:
                after = target.read_text(encoding="utf-8") if target.exists() else ""
            except UnicodeError:
                after = None
            if before is None or after is None or "\x00" in before or "\x00" in after:
                result.append({"path": name, "binary": True, "before": "", "after": ""})
                continue
            result.append({"path": name, "before": before, "after": after, "binary": False})
        return result

    def patch(self):
        self.changes()
        return git(self.root, "diff", "--cached", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", "--", ".")

    def rollback_to_patch(self, patch):
        git(self.root, "checkout", "-f", "HEAD")
        git(self.root, "clean", "-fd")
        if patch and isinstance(patch, str) and patch.strip():
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f:
                f.write(patch)
                temp_path = f.name
            try:
                git(self.root, "apply", "--whitespace=nowarn", temp_path)
            finally:
                Path(temp_path).unlink(missing_ok=True)
        return self.changes()

    def run_checks(self, argv, stop_event, timeout=90, on_output=None, on_raw=None):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 1800:
            raise ValueError("Verification timeout must be positive and at most 1800 seconds")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a and "\x00" not in a for a in argv):
            raise ValueError("Check command must be an argument list")
        started = time.monotonic()
        home = self.root.parent / "process-home"
        home.mkdir(exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k in {"PATH", "SystemRoot", "WINDIR", "LANG", "LC_ALL"}}
        env.update({"HOME": str(home), "TMPDIR": str(home), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1", "CI": "1", "NO_COLOR": "1", "GIT_TERMINAL_PROMPT": "0"})
        # Independent handles keep preview reads from moving the child's write
        # position. A disk spool avoids blocking a noisy child on a full pipe.
        with tempfile.TemporaryDirectory(prefix="cheapos-check-") as spool:
            path = Path(spool) / "output"
            with path.open("wb") as output, path.open("rb") as reader:
                process = subprocess.Popen(argv, cwd=str(self.root), env=env, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=os.name != "nt")
                reason, text, published, last_publish = None, "", None, 0
                decoder = codecs.getincrementaldecoder("utf-8")("replace")

                def preview(final=False):
                    nonlocal text, published, last_publish
                    text += decoder.decode(reader.read(max(0, 32_000 - reader.tell())), final=final)
                    truncated = os.fstat(output.fileno()).st_size > 32_000
                    if on_output and (text, truncated) != published and (final or time.monotonic() - last_publish >= .25):
                        on_output(text, truncated)
                        published, last_publish = (text, truncated), time.monotonic()
                    return truncated

                try:
                    while process.poll() is None:
                        preview()
                        if stop_event.wait(0.05):
                            reason = "cancelled"
                        elif time.monotonic() - started > timeout:
                            reason = "timed out"
                        elif os.fstat(output.fileno()).st_size > 2_000_000:
                            reason = "output limit exceeded"
                        if reason:
                            break
                finally:
                    # Also reap the process if publishing the preview fails.
                    if process.poll() is None:
                        try:
                            if os.name != "nt":
                                os.killpg(process.pid, signal.SIGKILL)
                            else:
                                process.kill()
                        except ProcessLookupError:
                            pass
                    process.wait()
                if os.fstat(output.fileno()).st_size > 2_000_000 and not reason:
                    reason = "output limit exceeded"
                truncated = preview(final=True)
                if on_raw:
                    with path.open("rb") as raw:
                        captured=raw.read(2_000_001)
                    on_raw(captured[:2_000_000], len(captured)>2_000_000)
        return {"command": argv, "exit_code": process.returncode, "passed": process.returncode == 0 and reason is None, "output": text, "truncated": truncated, "duration": round(time.monotonic() - started, 2), "reason": reason}
