"""Bounded, best-effort indexes into captured check bytes; never verdicts."""
import json
import re

VERSION = 1
SCAN_BYTES = 512_000
MAX_ITEMS = 80
INDEX_BYTES = 24_000
MAX_LINE = 8_000
MAX_TEXT = 800
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
# Recognize explicit reporter grammars, not arbitrary prose about errors.
TSC = re.compile(r'^(.*)\((\d{1,9}),(\d{1,9})\): (error|warning) (TS\d+): (.+)$')
TSC_PLAIN = re.compile(r'^(.*):(\d{1,9}):(\d{1,9}) - (error|warning) (TS\d+): (.+)$')
MYPY = re.compile(r'^(.*?):(\d{1,9})(?::(\d{1,9}))?: (error|warning|note): (.+?)(?:  \[([^\]]+)\])?$')
LINT = re.compile(r'^(.*?):(\d{1,9}):(\d{1,9}): ([A-Z]+\d+) (.+)$')
ESLINT = re.compile(r'^(.*?):(\d{1,9}):(\d{1,9}): (.+) \[(Error|Warning)/([^\]]+)\]$')
PYTEST = re.compile(r'^(FAILED|ERROR) (\S+::\S+)(?: - (.*))?$')
UNITTEST = re.compile(r'^(FAIL|ERROR): (\S+) \(([^\n]+)\)$')


def _match(line):
    match = TSC.fullmatch(line) or TSC_PLAIN.fullmatch(line)
    if match:
        path, row, column, severity, name, message = match.groups()
        return 'typescript', path, row, column, name, severity, message
    match = MYPY.fullmatch(line)
    if match:
        path, row, column, severity, message, name = match.groups()
        return 'python-type', path, row, column, name, severity, message
    match = LINT.fullmatch(line)
    if match:
        path, row, column, name, message = match.groups()
        # Rule prefixes don't reliably encode severity across linters.
        return 'python-lint', path, row, column, name, 'unknown', message
    match = ESLINT.fullmatch(line)
    if match:
        path, row, column, message, severity, name = match.groups()
        return 'eslint-unix', path, row, column, name, severity.lower(), message
    match = PYTEST.fullmatch(line)
    if match:
        severity, name, message = match.groups()
        return 'pytest', name.split('::', 1)[0], None, None, name, 'error', message or severity
    match = UNITTEST.fullmatch(line)
    if match:
        severity, name, owner = match.groups()
        return 'unittest', None, None, None, owner if owner.endswith('.' + name) else owner + '.' + name, 'error', severity
    return None


def parse(data, run_id, *, truncated=False):
    """Offsets refer to original retained bytes, including ANSI and CRLF.

    File paths are reporter text relative to the receipt's working directory;
    they are never resolved or read. Missing locations/severity stay unknown.
    """
    clipped = len(data) > SCAN_BYTES
    sample = data[:SCAN_BYTES]
    items, formats = [], set()
    offset = 0
    index_bytes = 0
    limited = clipped or truncated
    for raw in sample.splitlines(keepends=True):
        end = offset + len(raw)
        # Don't parse a line cut by capture/scan boundaries or pathological lines.
        if len(raw) > MAX_LINE or (end == len(sample) and (clipped or truncated) and not raw.endswith(b'\n')):
            limited = True
            offset = end
            continue
        line = ANSI.sub('', raw.decode('utf-8', 'replace')).rstrip('\r\n')
        found = _match(line)
        if found:
            if len(items) == MAX_ITEMS:
                limited = True
                break
            kind, path, row, column, name, severity, message = found
            def bounded(value):
                return value[:MAX_TEXT] if value is not None else None
            item = {'path': bounded(path), 'line': int(row) if row else None,
                          'column': int(column) if column else None, 'name': bounded(name),
                          'severity': severity, 'message': bounded(message),
                          'text_truncated': any(value and len(value) > MAX_TEXT for value in (path, name, message)),
                          'raw_evidence': {'run_id': run_id, 'offset': offset, 'end_offset': end}}
            size = len(json.dumps(item, ensure_ascii=False).encode())
            if index_bytes + size > INDEX_BYTES:
                limited = True
                break
            index_bytes += size
            items.append(item)
            formats.add(kind)
        offset = end
    return {'version': VERSION, 'status': 'partial' if limited else 'recognized' if items else 'unparsed',
            'formats': sorted(formats), 'items': items, 'scanned_bytes': offset,
            'limited': limited, 'note': 'Best-effort diagnostic index, not a verdict or exhaustive failure list. '
            'Use this run’s original output and authoritative status; paths are reporter text relative to its working directory.'}


def from_file(path, run_id, truncated=False):
    with path.open('rb') as stream:
        data = stream.read(SCAN_BYTES + 1)
    return parse(data, run_id, truncated=truncated)
