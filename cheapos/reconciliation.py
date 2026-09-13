"""Rebuild a task copy against the current project without writing to the source."""

import subprocess
from pathlib import Path

from . import commits
from .workspace import Workspace, git


def entry(workspace, name, baseline=False):
    """An absent file differs from an empty file; preserve executable modes too."""
    path = workspace.path(name)
    if baseline:
        listing = git(workspace.root, "ls-tree", "-z", "HEAD", "--", name)
        if not listing:
            return None
        mode = listing.split(" ", 1)[0]
        data = git(workspace.root, "show", "HEAD:" + name, binary=True)
    else:
        if not path.exists():
            return None
        if not path.is_file():
            raise ValueError("Cannot reconcile a file with a directory: " + name)
        data = path.read_bytes()
        mode = "100755" if path.stat().st_mode & 0o111 else "100644"
    if mode not in {"100644", "100755"} or b"\x00" in data or len(data) > 2_000_000:
        raise ValueError("Reconciliation supports regular text files only: " + name)
    data.decode("utf-8")
    return data, mode


def build(task, destination):
    state = commits.source_state(task["source"])
    commits.require_clean(state["source"])
    old = Workspace(task["workspace"])
    fresh, _ = Workspace.snapshot(state["source"], destination)
    conflicts = []
    for change in task["changes"]:
        name = change["path"]
        # Checking the real source also rejects paths omitted by snapshot rules.
        project = entry(Workspace(state["source"]), name)
        current = entry(fresh, name)
        if project != current:
            raise ValueError("This file could not be copied safely into the task: " + name)
        before, saved = entry(old, name, baseline=True), entry(old, name)
        if current == saved or saved == before:
            continue
        if current == before:
            merged = saved
        else:
            # Distinct mode edits cannot be silently resolved by a text merge.
            if current and saved and current[1] != saved[1] and (not before or before[1] not in {current[1], saved[1]}):
                raise ValueError("Resolve conflicting file permissions before reconciling: " + name)
            parts = []
            for label, item in (("project", current), ("base", before), ("task", saved)):
                path = Path(destination).parent / ("merge-" + label)
                path.write_bytes(item[0] if item else b"")
                parts.append(str(path))
            result = subprocess.run(["git", "merge-file", "-p", "--diff3", "-L", "CURRENT PROJECT", "-L", "TASK BASELINE", "-L", "SAVED TASK", *parts],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            for path in parts:
                Path(path).unlink()
            if result.returncode < 0 or result.returncode > 127:
                raise ValueError("Could not combine the text versions of " + name)
            if result.returncode:
                conflicts.append(name)
            mode = saved[1] if saved and (not before or saved[1] != before[1]) else (current or saved)[1]
            merged = (result.stdout, mode)
            # A clean delete/modify merge with no remaining text is a deletion.
            if not result.returncode and not result.stdout and (current is None or saved is None):
                merged = None
        target = fresh.path(name)
        if merged is None:
            target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(merged[0])
            target.chmod(0o700 if merged[1] == "100755" else 0o600)
    if commits.source_state(state["source"]) != state:
        raise ValueError("The project changed during reconciliation. Retry using its current version.")
    commits.require_clean(state["source"])
    return {"source_head": state["head"], "branch": state["branch"], "previous_workspace": task["workspace"],
            "workspace": str(fresh.root), "conflicts": conflicts, "files": [f["path"] for f in task["changes"]]}


def ensure_resolved(task):
    workspace = Workspace(task["workspace"])
    for name in task.get("reconciliation", {}).get("conflicts", []):
        path = workspace.path(name)
        if path.exists() and any(line.startswith(("<<<<<<< CURRENT PROJECT", "||||||| TASK BASELINE", ">>>>>>> SAVED TASK"))
                                 for line in path.read_text().splitlines()):
            raise ValueError("Resolve the project/task conflict markers in " + name + " before checks or review. Both versions are in this task copy.")


def guidance(task):
    info = task.get("reconciliation")
    if not info:
        return ""
    review = (task.get("checkpoints") or [{}])[-1]
    if review.get("generation", 0) == task.get("workspace_generation", 0) and review.get("decision") == "APPROVE":
        return ""
    check = (task.get("checks") or [{}])[-1]
    if task.get("status") == "completed" and check.get("generation", 0) == task.get("workspace_generation", 0) and check.get("passed"):
        return ""
    return ("This task copy was refreshed from the current project at " + info["source_head"][:8] + ". "
            "The operator requested reconciliation of the saved edits in " + ", ".join(info["files"]) + ". "
            "Resolve any CURRENT PROJECT / TASK BASELINE / SAVED TASK conflict markers. "
            "Preserve existing project behavior and tests while satisfying the user's original request for these files; "
            "do not blindly replace the project with the saved version. Earlier checks and reviews describe an older task copy. "
            "Run the relevant tests for the affected files, then submit a new checkpoint. If there are no remaining changes, explain that they are already in the project.")
