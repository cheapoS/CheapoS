#!/usr/bin/env python3
"""Select development checks from changed files without changing app verification."""
import argparse
import ast
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git_files(root, base=None):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root).decode('utf-8').split('\0')
    names = git('diff', '--name-only', '--no-renames', '-z', 'HEAD')
    names += git('ls-files', '--others', '--exclude-standard', '-z')
    if base:
        names += git('diff', '--name-only', '--no-renames', '-z', base + '...HEAD')
    return sorted(set(filter(None, names)))


def python_tests(root, changed):
    """Conservative reverse import closure, including shared test helpers."""
    paths = sorted([*root.glob('cheapos/**/*.py'), *root.glob('scripts/**/*.py'),
                    *root.glob('tests/**/*.py'), *root.glob('*.py')])
    modules = {}
    for path in paths:
        relative = path.relative_to(root)
        name = '.'.join(relative.with_suffix('').parts)
        if name.endswith('.__init__'): name = name[:-9]
        modules[name] = relative.as_posix()
        if relative.parts[0] in {'tests', 'scripts'}:
            modules[path.stem] = relative.as_posix()
    edges = {}
    for path in paths:
        relative = path.relative_to(root).as_posix()
        try: tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeError):
            # Syntax errors must not silently narrow a test selection.
            return sorted(p.relative_to(root).as_posix() for p in root.glob('tests/test_*.py')), ['Python syntax/import analysis could not complete; select all Python modules.']
        dependencies = set()
        package = list(Path(relative).parent.parts)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import): names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                prefix = '.'.join(package[:len(package)-node.level+1]) if node.level else ''
                base = '.'.join(filter(None, [prefix, node.module]))
                names = [base] + ['.'.join(filter(None, [base, alias.name])) for alias in node.names]
            for name in names:
                pieces = name.split('.')
                while pieces:
                    if '.'.join(pieces) in modules:
                        dependencies.add(modules['.'.join(pieces)])
                        break
                    pieces.pop()
        edges[relative] = dependencies
    # Entry points launched by subprocess/importlib cannot appear as static imports.
    extra = {'tests/test_dev_tests.py': {'scripts/dev_tests.py', 'scripts/parallel_tests.py'},
             'tests/test_check_selection.py': {'scripts/check.py'},
             'tests/test_word_count.py': {'scripts/word_count.py'},
             'tests/test_time_ago.py': {'scripts/time_ago.py'},
             'tests/test_csv_to_md.py': {'scripts/csv_to_md.py'}}
    for path, dependencies in extra.items():
        if path in edges: edges[path].update(dependencies)
    affected = set(changed)
    while True:
        more = {path for path, dependencies in edges.items() if dependencies & affected}
        if more <= affected: break
        affected.update(more)
    tests = sorted(path for path in affected if path.startswith('tests/') and Path(path).name.startswith('test_') and (root/path).is_file())
    unmatched = [path for path in changed if not any(path in deps for deps in edges.values())
                 and not (path.startswith('tests/test_') and (root/path).is_file())]
    if unmatched:
        return sorted(p.relative_to(root).as_posix() for p in root.glob('tests/test_*.py')), ['No known import/test coverage for '+', '.join(unmatched)+'; select all Python modules.']
    return tests, []


def plan(root, files, jobs=4, full=False):
    files = sorted(set(files))
    commands, notes = [], []
    frontend = full or any(path.startswith('dist/') or path.startswith('tests/') and path.endswith('.js') for path in files)
    backend = [path for path in files if path.endswith('.py')]
    unknown = [path for path in files if not (path.endswith(('.py', '.md')) or path.startswith(('docs/', 'dist/'))
               or path in {'AGENTS.md','CONTRIBUTING.md','LICENSE','.gitignore'} or path.startswith('tests/') and path.endswith('.js'))]
    if files or full: commands.append(['git', 'diff', '--check'])
    if frontend:
        commands += [['node', '--check', path.relative_to(root).as_posix()] for path in sorted((root/'dist').glob('*.js'))]
        javascript = [path.relative_to(root).as_posix() for path in sorted((root/'tests').glob('test_*.js'))]
        if javascript: commands.append(['node', '--test', *javascript])
        notes.append('Exercise the affected browser flow with disposable data; this command does not automate browser acceptance.')
    selected = []
    if full or unknown:
        selected = [path.relative_to(root).as_posix() for path in sorted((root/'tests').glob('test_*.py'))]
        if unknown: notes.append('Unmapped runtime/configuration changes: '+', '.join(unknown)+'; select all Python modules.')
    elif backend:
        selected, reasons = python_tests(root, backend)
        notes.extend(reasons)
    if selected:
        command = [sys.executable, '-B', 'scripts/dev_tests.py', '--jobs', str(jobs), '--timings']
        for path in selected: command.extend(['--pattern', Path(path).name])
        commands.append(command)
    elif backend or full:
        raise ValueError('No Python tests found for this selection; verification cannot be reported as passing.')
    if files and not frontend and not backend and not unknown:
        notes.append('Documentation-only selection: inspect edited links/examples; no runtime tests selected.')
    if not files and not full:
        notes.append('No changed files. No tests run. Use --base main for committed branch changes, or --files for explicit paths.')
    return commands, notes, selected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', help='Include committed changes since the merge base with this ref (e.g. main)')
    parser.add_argument('--files', nargs='+', help='Explicit repository-relative changed files instead of Git detection')
    parser.add_argument('--plan', action='store_true', help='Show checks without executing them')
    parser.add_argument('--full', action='store_true', help='Explicit complete Python and JavaScript regression')
    parser.add_argument('--jobs', type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args(argv)
    if not 1 <= args.jobs <= 16: parser.error('--jobs must be between 1 and 16')
    try:
        files = args.files if args.files is not None else git_files(ROOT, args.base)
        if any(Path(path).is_absolute() or '..' in Path(path).parts for path in files):
            raise ValueError('Use repository-relative paths without traversal')
        commands, notes, selected = plan(ROOT, files, args.jobs, args.full)
    except (ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    print('Changed files: '+(', '.join(files) or '(none)'), flush=True)
    print(f'Selected {len(selected)} Python modules; {args.jobs} maximum workers.', flush=True)
    for note in notes: print(note, flush=True)
    for command in commands:
        print('$ '+shlex.join(command), flush=True)
        if not args.plan:
            result = subprocess.run(command, cwd=ROOT)
            if result.returncode: return result.returncode
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except KeyboardInterrupt:
        print('\nChecks cancelled.', file=sys.stderr)
        raise SystemExit(130)
