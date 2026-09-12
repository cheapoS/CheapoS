"""Repository snapshots and constrained file tools. Check commands are NOT OS-sandboxed."""

import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path, PurePosixPath


MAX_FILE_BYTES = 256_000
MAX_SNAPSHOT_BYTES = 100_000_000
MAX_FILES = 5000
BLOCKED_PARTS = {".git", ".cheapos", ".ssh", ".aws", ".gnupg", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
BLOCKED_NAMES = {".env", ".npmrc", ".pypirc", ".netrc", "id_rsa", "id_ed25519", "credentials", "credentials.json"}


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

    @classmethod
    def snapshot(cls, source, destination):
        source = Path(source).expanduser().resolve(strict=True)
        if not source.is_dir():
            raise ValueError("Choose a local Git repository directory")
        top = Path(git(source, "rev-parse", "--show-toplevel").strip()).resolve()
        if top != source:
            raise ValueError("Choose the root of the Git repository: " + str(top))
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
        git(destination, "-c", "user.name=CheapOS", "-c", "user.email=local@cheapos.invalid", "commit", "-qm", "Local task baseline")
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

    def list_files(self):
        names = git(self.root, "ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")
        return sorted(n for n in set(names) if n and allowed_name(n) and not (self.root / n).is_symlink())[:MAX_FILES]

    def read_file(self, path, start_line=1, end_line=200):
        target = self.path(path)
        if not target.is_file():
            raise ValueError("File not found")
        if target.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("File is too large for the text tools")
        if not isinstance(start_line, int) or not isinstance(end_line, int) or start_line < 1 or end_line < start_line:
            raise ValueError("Invalid line range")
        text = target.read_text(encoding="utf-8")
        if "\x00" in text:
            raise ValueError("Binary files cannot be read by the text tools")
        lines = text.splitlines()
        end_line = min(end_line, start_line + 299)
        return {"path": path, "total_lines": len(lines), "content": "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines) if start_line - 1 <= i < end_line)[:20_000]}

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
            raise ValueError("File already exists; use replace_text for existing files")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        target.chmod(0o600)
        return {"path": path, "created": True}

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
        return {"path": path, "updated": True}

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

    def run_checks(self, argv, stop_event, timeout=90):
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a and "\x00" not in a for a in argv):
            raise ValueError("Check command must be an argument list")
        started = time.monotonic()
        home = self.root.parent / "process-home"
        home.mkdir(exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k in {"PATH", "SystemRoot", "WINDIR", "LANG", "LC_ALL"}}
        env.update({"HOME": str(home), "TMPDIR": str(home), "PYTHONDONTWRITEBYTECODE": "1", "CI": "1", "NO_COLOR": "1", "GIT_TERMINAL_PROMPT": "0"})
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(argv, cwd=str(self.root), env=env, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=os.name != "nt")
            reason = None
            while process.poll() is None:
                if stop_event.wait(0.05):
                    reason = "cancelled"
                elif time.monotonic() - started > timeout:
                    reason = "timed out"
                elif output.tell() > 2_000_000:
                    reason = "output limit exceeded"
                if reason:
                    try:
                        if os.name != "nt":
                            os.killpg(process.pid, signal.SIGKILL)
                        else:
                            process.kill()
                    except ProcessLookupError:
                        pass
                    break
            process.wait()
            output.seek(0)
            text = output.read(32_000).decode("utf-8", errors="replace")
        return {"command": argv, "exit_code": process.returncode, "passed": process.returncode == 0 and reason is None, "output": text, "duration": round(time.monotonic() - started, 2), "reason": reason}
