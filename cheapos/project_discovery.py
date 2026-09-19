"""Shared repository facts. Discovery never imports config or runs project commands."""
import json
import re
import shlex
from pathlib import PurePosixPath

VERSION = 1
GUIDANCE = {'AGENTS.md', 'CONTRIBUTING.md'}
MANIFESTS = {'package.json', 'pyproject.toml', 'requirements.txt', 'Cargo.toml',
             'go.mod', 'Gemfile', 'composer.json', 'pom.xml', 'build.gradle',
             'build.gradle.kts', 'settings.gradle', 'settings.gradle.kts',
             'Makefile', 'CMakeLists.txt', 'deno.json', 'deno.jsonc', 'mix.exs',
             'Package.swift', 'pubspec.yaml'}
LOCKS = {'package-lock.json', 'npm-shrinkwrap.json', 'pnpm-lock.yaml', 'yarn.lock',
         'bun.lock', 'bun.lockb', 'uv.lock', 'poetry.lock', 'Cargo.lock', 'go.sum'}


def kind(path):
    name = PurePosixPath(path).name
    if name in GUIDANCE or path == '.cheapos/rules.md':
        return 'guidance'
    if name in MANIFESTS or PurePosixPath(name).suffix in {'.csproj', '.fsproj', '.sln'}:
        return 'manifest'
    if name.lower() == 'readme' or (PurePosixPath(name).stem.lower() == 'readme'
            and PurePosixPath(name).suffix.lower() in {'.md', '.mdx', '.rst', '.txt', '.adoc', '.markdown'}):
        return 'readme'
    if name in LOCKS:
        return 'lockfile'
    return None


def permitted_files(workspace):
    names = []
    for name in workspace.list_files():
        try:
            workspace.path(name)  # Includes symlinked parents, not just leaf links.
        except ValueError:
            continue
        names.append(name)
    return sorted(set(names))


def source_paths(names):
    """Guidance precedes manifests and README at each directory depth."""
    priority = {'guidance': 0, 'manifest': 1, 'readme': 2}
    return sorted((n for n in names if kind(n) in priority), key=lambda n: (
        0 if n == '.cheapos/rules.md' else len(PurePosixPath(n).parts),
        priority[kind(n)], n))


def inventory(names, scope='.', component_limit=32):
    """Describe components by file evidence; do not guess which one is the app."""
    paths = [n for n in names if scope == '.' or n.startswith(scope + '/')]
    groups = {scope: {'path': scope, 'manifests': [], 'guidance': [], 'readmes': [], 'lockfiles': []}}
    labels = {'manifest': 'manifests', 'guidance': 'guidance', 'readme': 'readmes', 'lockfile': 'lockfiles'}
    for name in paths:
        category = kind(name)
        if category is None:
            continue
        parent = str(PurePosixPath(name).parent)
        if name == '.cheapos/rules.md':
            parent = '.'
        group = groups.setdefault(parent, {'path': parent, 'manifests': [], 'guidance': [], 'readmes': [], 'lockfiles': []})
        group[labels[category]].append(name)
    ordered = sorted(groups.values(), key=lambda g: (
        g['path'] != scope, not bool(g['manifests'] or g['guidance']),
        len(PurePosixPath(g['path']).parts), g['path']))
    components = []
    for group in ordered[:component_limit]:
        omitted = sum(max(0, len(group[key]) - 8) for key in labels.values())
        components.append({**{key: value[:8] if isinstance(value, list) else value for key, value in group.items()},
                           'omitted_paths': omitted})
    return {'version': VERSION, 'scope': scope, 'file_count': len(paths),
            'components': components, 'component_count': len(ordered),
            'omitted_components': max(0, len(ordered) - len(components)),
            'meaning': 'Directories are evidence locations, not an asserted application root. Guidance applies within its directory subtree. A README or preview URL alone does not identify the active app.',
            'continuation': 'Inspect a listed directory for its scoped map and paginated paths; inspect named files for complete content. Missing manifests do not mean an empty or unsupported project.'}


def package_scripts(document, names):
    """Expose declared scripts and their cwd, not an execution allowlist."""
    path = document.get('path', '')
    if PurePosixPath(path).name != 'package.json' or document.get('truncated'):
        return []
    try:
        value = json.loads(document.get('contents', ''))
    except (TypeError, ValueError):
        return []
    if not isinstance(value, dict) or not isinstance(value.get('scripts'), dict):
        return []
    parent = PurePosixPath(path).parent
    managers = set()
    declared = value.get('packageManager', '')
    if isinstance(declared, str) and declared.split('@')[0] in {'npm', 'pnpm', 'yarn', 'bun'}:
        managers.add(declared.split('@')[0])
    for lock, manager in [('package-lock.json', 'npm'), ('npm-shrinkwrap.json', 'npm'),
                          ('pnpm-lock.yaml', 'pnpm'), ('yarn.lock', 'yarn'), ('bun.lock', 'bun'), ('bun.lockb', 'bun')]:
        if str(parent / lock) in names:
            managers.add(manager)
    rows = []
    for name, script in value['scripts'].items():
        if isinstance(script, str) and re.fullmatch(r'(?:test|check|lint|typecheck|type-check|build|verify|validate)(?::[\w:.-]+)?', name):
            rows.append({'source': path, 'field': 'scripts.' + name, 'cwd': str(parent),
                         'name': name, 'script': script[:500], 'truncated': len(script) > 500,
                         'package_managers': sorted(managers), 'authority': 'Declared, unverified script; not permission to execute it.'})
    return rows


def command_evidence(document):
    """Retain exact command-shaped source spans for missing-runner diagnosis.

    This is provenance, never a command permission or an assertion of safety.
    Shell syntax and execution authority are still checked by their owners.
    """
    content = document.get('contents', '')
    if not isinstance(content, str):
        return []
    spans = re.findall(r'(?<!`)`([^`\n]+)`(?!`)', content)
    spans += [line.strip().removeprefix('$ ') for line in content.splitlines()]
    rows = []
    # A missing runner must be declared, not merely invented by the planner.
    # Package-manager metadata establishes a runner, but grants no permission
    # to invoke any script. Approval still validates the exact proposed argv.
    for script in package_scripts(document, []):
        for manager in script['package_managers']:
            row = {'source': script['source'], 'runner': manager}
            if row not in rows:
                rows.append(row)
    for span in spans:
        if len(span) > 4000:
            continue
        try:
            argv = shlex.split(span)
        except ValueError:
            continue
        if argv and argv not in [row.get('argv') for row in rows]:
            rows.append({'source': document.get('path', 'direct request'), 'argv': argv})
    return rows


def check_is_grounded(argv, evidence):
    return any(row.get('argv') == argv or row.get('runner') == argv[0] for row in evidence)
