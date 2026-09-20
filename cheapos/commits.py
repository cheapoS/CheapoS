"""User-approved local Git handoff. This is deliberately not a model tool."""

import os
import subprocess
import tempfile
from pathlib import Path

from .workspace import Workspace, git


class ProjectConflict(ValueError):
    code = "project_conflict"

    def __init__(self, files):
        self.files = files
        super().__init__("These edits overlap changes already in your project. Reconcile in this chat to combine both versions, then run checks and review again. Your saved work is intact.")


# App-level fallback identity. Any key already resolvable through the
# repository's local or global Git configuration wins; these values only cover
# keys Git would otherwise reject with "Please tell me who you are."
DEFAULT_IDENTITY = {"user.name": "cheapos", "user.email": "team@cheapos.lol"}


def source_git(source, *args, input=None, index=None):
    # Use the operator's Git identity, but never run hooks, signing or a shell.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    if index:
        env["GIT_INDEX_FILE"] = str(index)
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgSign=false",
         "-c", "core.fsmonitor=false", *args], cwd=source, env=env,
        input=input.encode() if isinstance(input, str) else input,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace").strip()[:1000] or "Git command failed")
    return result.stdout.decode(errors="replace").strip()


def identity_flags(source, git_settings=None):
    """Flags that supply fallback identity if Git cannot resolve it."""
    flags = []
    for git_key, default_value in DEFAULT_IDENTITY.items():
        setting_key = git_key.replace(".", "_")
        value = (git_settings or {}).get(setting_key) or default_value
        try:
            have = source_git(source, "config", "--get", git_key)
        except ValueError:
            have = ""
        if not have.strip():
            flags.extend(["-c", f"{git_key}={value}"])
    return flags


def source_state(source):
    source = str(Workspace.project_root(source))
    try:
        branch = source_git(source, "symbolic-ref", "--quiet", "HEAD")
        head = source_git(source, "rev-parse", "HEAD")
    except ValueError:
        raise ValueError("Check out a branch with an initial commit before applying changes") from None
    markers = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "sequencer")
    args = [arg for marker in markers for arg in ("--git-path", marker)]
    for raw in source_git(source, "rev-parse", *args).splitlines():
        path = Path(raw)
        if (path if path.is_absolute() else Path(source) / path).exists():
            raise ValueError("Finish the Git operation already in progress before applying changes")
    keys = source_git(source, "config", "--list", "--name-only").splitlines()
    if any(k.startswith("filter.") and k.endswith((".clean", ".smudge", ".process")) for k in keys):
        raise ValueError("This repository uses Git content filters. Export the patch for its normal Git workflow.")
    if any(line[:1] == "S" or line[:1].islower() for line in source_git(source, "ls-files", "-v").splitlines()):
        raise ValueError("Expand the sparse checkout and clear skip-worktree/assume-unchanged flags before applying changes")
    return {"source": source, "branch": branch, "head": head}


def require_clean(source):
    if source_git(source, "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"):
        raise ValueError("Your project has uncommitted changes. Commit or move them first, then reopen Apply & commit. cheapoS will keep this task's edits saved.")


def prepare(task):
    state = source_state(task["source"])
    source = state["source"]
    require_clean(source)
    files = [f["path"] for f in task["changes"]]
    for name in files:
        Workspace(source).path(name)
    # A temporary index checks and constructs the exact tree without staging in
    # the real checkout. No model call, worktree write, or commit happens here.
    with tempfile.TemporaryDirectory(prefix="cheapos-commit-") as tmp:
        index = Path(tmp) / "index"
        source_git(source, "read-tree", state["head"], index=index)
        try:
            source_git(source, "apply", "--cached", "--check", "--whitespace=nowarn", "-", input=task["patch"], index=index)
        except ValueError as error:
            raise ProjectConflict(files) from error
        source_git(source, "apply", "--cached", "--whitespace=nowarn", "-", input=task["patch"], index=index)
        tree = source_git(source, "write-tree", index=index)
    # The commit identity is chosen by the operator's Git configuration; any
    # missing key falls back to the app default so approval never dead-ends.
    git_settings = task.get("settings_snapshot", {}).get("values", {}).get("git")
    identity_flags(source, git_settings=git_settings)
    if source_state(source) != state:
        raise ValueError("Your branch changed while preparing the preview. Open Apply & commit again.")
    require_clean(source)
    return {**state, "tree": tree, "patch": task["patch"], "files": files, "git_settings": git_settings}


def staged_exactly(plan):
    source = plan["source"]
    return (source_git(source, "write-tree") == plan["tree"]
            and not source_git(source, "diff", "--no-ext-diff", "--no-textconv", "--name-only")
            and not source_git(source, "ls-files", "--others", "--exclude-standard"))


def transaction_state(plan):
    state = source_state(plan["source"])
    if state["branch"] != plan["branch"]:
        raise ValueError("The project branch changed. Return to the approved branch before retrying the commit.")
    if state["head"] == plan["commit"]:
        return "committed"
    if state["head"] != plan["head"]:
        raise ValueError("The project moved to another commit. Inspect the saved commit attempt before continuing.")
    if staged_exactly(plan):
        return "staged"
    require_clean(plan["source"])
    return "clean"


def commit_object(plan, message):
    return source_git(plan["source"], *identity_flags(plan["source"], git_settings=plan.get("git_settings")), "commit-tree", plan["tree"], "-p", plan["head"], input=message + "\n")


def apply_and_commit(plan):
    stage = transaction_state(plan)
    if stage == "committed":
        return
    if stage == "clean":
        source_git(plan["source"], "apply", "--index", "--whitespace=nowarn", "-", input=plan["patch"])
    if transaction_state(plan) != "staged":
        raise ValueError("The project changed during the commit. Saved edits were kept; inspect the project before retrying.")
    # The commit contains only the prepared tree. Compare-and-swap prevents
    # moving a branch that another Git operation advanced in the meantime.
    source_git(plan["source"], "update-ref", "-m", "cheapoS: " + plan["message"].splitlines()[0],
               plan["branch"], plan["commit"], plan["head"])


def advance_workspace(task, plan):
    current = git(task["workspace"], "rev-parse", "HEAD").strip()
    if current == plan["workspace_commit"]:
        return
    if current != plan["workspace_head"]:
        raise ValueError("The source commit succeeded, but the task baseline changed. Inspect the saved commit before continuing.")
    git(task["workspace"], "update-ref", "HEAD", plan["workspace_commit"], current)


def workspace_commit(task):
    head = git(task["workspace"], "rev-parse", "HEAD").strip()
    tree = git(task["workspace"], "write-tree").strip()
    commit = git(task["workspace"], "-c", "user.name=cheapoS", "-c", "user.email=local@cheapos.invalid",
                 "commit-tree", tree, "-p", head, "-m", "Applied approved changes to source project").strip()
    return {"workspace_head": head, "workspace_commit": commit}
