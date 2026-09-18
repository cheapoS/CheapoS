"""Pure filesystem-aware unittest profile matching; never executes commands.

Profile schema: {schema_version: 1, runner: 'unittest', project: <identity>,
executable: <resolved Python path>, roots: ['tests', ...]}.
Only optional Python -B, -m unittest, -v/-q/-f/-b, explicit discovery with
-s/-p/-t, dotted module/class/method selectors, and Python file paths are supported. A match is
not authorization: the controller must separately obtain a session grant.
Tests execute repository code, including edited code; this is not a sandbox.
"""
import re
import shutil
from pathlib import Path

FLAGS = {'-v', '-q', '-f', '-b'}
IDENTIFIER = re.compile(r'^[A-Za-z_]\w*$', re.ASCII)


def unittest_selection(argv):
    """Match explicit checks differing only in -B or verbosity, not grant them.

    Keep the interpreter, selectors (including file paths), their order and
    execution flags exact. Discovery, filters and unfamiliar options deliberately
    have no key. A caller must execute an already-authorized original command,
    never use this key to authorize the requested variant.
    """
    if not isinstance(argv, (list, tuple)) or not argv or any(not isinstance(a, str) or not a or '\0' in a for a in argv):
        return None
    args = list(argv[1:])
    if args[:1] == ['-B']:
        args.pop(0)
    if args[:2] != ['-m', 'unittest']:
        return None
    selected = []
    for arg in args[2:]:
        if arg in {'-v', '-q', '--verbose', '--quiet'}:
            continue
        if arg == 'discover' or (arg.startswith('-') and arg not in {'-f', '-b'}):
            return None
        selected.append(arg)
    if not any(not arg.startswith('-') for arg in selected):
        return None
    return (argv[0], *selected)


def executable_identity(value, workspace):
    if not isinstance(value, str) or not value or '\x00' in value:
        return None
    candidate = value if Path(value).is_absolute() else (str(Path(workspace) / value) if '/' in value else shutil.which(value))
    if not candidate:
        return None
    try:
        invoked = Path(candidate).absolute()
        path = invoked if (invoked.parent.parent / 'pyvenv.cfg').is_file() else invoked.resolve(strict=True)
        return str(path) if path.is_file() else None
    except (OSError, ValueError):
        return None


def inside(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def scoped_path(value, workspace):
    if not isinstance(value, str) or not value or '\x00' in value or '..' in Path(value).parts:
        raise ValueError('Invalid or traversing path')
    path = (workspace / value).resolve(strict=True)
    if not inside(path, workspace):
        raise ValueError('Path leaves the task workspace')
    return path


def match_unittest(argv, workspace, profile):
    def no(reason): return {'matched': False, 'reason': reason}
    if not isinstance(argv, (list, tuple)) or not argv or any(not isinstance(a, str) or not a or '\x00' in a for a in argv):
        return no('Invalid command arguments')
    if not isinstance(profile, dict) or type(profile.get('schema_version')) is not int or profile.get('schema_version') != 1 or profile.get('runner') != 'unittest':
        return no('Unsupported runner profile')
    try:
        root = Path(workspace).resolve(strict=True)
        roots = profile.get('roots')
        if not isinstance(roots, list) or not roots:
            return no('No approved test roots')
        approved = [scoped_path(value, root) for value in roots]
        if any(not path.is_dir() for path in approved):
            return no('Approved test root is unavailable')
        if executable_identity(argv[0], root) != profile.get('executable') or not profile.get('executable'):
            return no('Python executable differs from the approved profile')
        args = list(argv[1:])
        if args[:1] == ['-B']:
            args.pop(0)
        if args[:2] != ['-m', 'unittest']:
            return no('Command is not the approved unittest entry point')
        args = args[2:]
        # Global supported runner flags may precede discovery or selectors.
        while args and args[0] in FLAGS:
            args.pop(0)
        if not args or args[0] == 'discover':
            if args:
                args.pop(0)
            options = {}
            while args:
                arg = args.pop(0)
                if arg in FLAGS:
                    continue
                if arg not in {'-s', '-p', '-t'} or arg in options or not args:
                    return no('Unknown, repeated, or incomplete discovery option')
                options[arg] = args.pop(0)
            start = scoped_path(options.get('-s', '.'), root)
            if not start.is_dir() or not any(inside(start, allowed) for allowed in approved):
                return no('Discovery root is outside approved test roots')
            for entry in start.rglob('*'):
                if entry.is_symlink() and not any(inside(entry.resolve(strict=True), allowed) for allowed in approved):
                    return no('Discovery contains a symlink outside approved test roots')
            if '-t' in options:
                top = scoped_path(options['-t'], root)
                if not top.is_dir() or not inside(start, top):
                    return no('Top-level import root does not contain the tests')
            pattern = options.get('-p', 'test*.py')
            if any(c in pattern for c in '/\\\x00') or pattern in {'.', '..'}:
                return no('Test pattern must be a filename glob')
        else:
            selectors = [arg for arg in args if arg not in FLAGS]
            if not selectors:
                return no('No supported test selector')
            for selector in selectors:
                # unittest accepts file paths, but not pytest-style path:method
                # selectors. Unknown flags must never become projected paths.
                if ':' in selector or selector.startswith('-'):
                    return no('Unsupported test selector or runner flag')
                file_part = selector
                if file_part.endswith('.py') or '/' in file_part or '\\' in file_part:
                    if any(c in file_part for c in '\x00') or '..' in Path(file_part).parts:
                        return no('Path leaves the task workspace')
                    try:
                        target = (root / file_part).resolve()
                    except (ValueError, OSError):
                        return no('Invalid path selector')
                    if not inside(target, root) or not any(inside(target, allowed) for allowed in approved):
                        return no('Selector does not resolve inside approved test roots')
                    if target.suffix != '.py':
                        return no('Test selector must be a Python test file (.py)')
                else:
                    parts = selector.split('.')
                    if not all(IDENTIFIER.fullmatch(part) for part in parts):
                        return no('Unsupported test selector or runner flag')
                    found = None
                    for count in range(len(parts), 0, -1):
                        module = root.joinpath(*parts[:count]).with_suffix('.py')
                        if module.exists():
                            found = module.resolve(strict=True)
                            break
                        package = root.joinpath(*parts[:count]) / '__init__.py'
                        if package.exists():
                            found = package.resolve(strict=True)
                            break
                    if found is None or not inside(found, root) or not any(inside(found, allowed) for allowed in approved):
                        return no('Selector does not resolve inside approved test roots')
        return {'matched': True, 'reason': 'Supported unittest command within approved roots'}
    except (OSError, ValueError, TypeError):
        return no('Test root is missing, invalid, or outside the workspace')
