"""Represent current file excerpts honestly across worker handoffs."""
import hashlib


def file_excerpt(path, data, requests, maximum):
    lines = data.decode('utf-8').splitlines()
    numbered = [f'{i}: {line}' for i, line in enumerate(lines, 1)]
    full = '\n'.join(numbered)
    base = {'path': path, 'hash': hashlib.sha256(data).hexdigest(), 'total_lines': len(lines)}
    if len(full) <= maximum:
        return {**base, 'content': full, 'start_line': 1, 'end_line': len(lines), 'complete': True}
    # Keep several inspected regions, not only whichever header was read last.
    selected, remaining = {}, maximum
    unique, seen = [], set()
    for request in requests:
        key = (request.get('start_line', 1), request.get('end_line'))
        if key not in seen:
            unique.append(request)
            seen.add(key)
        if len(unique) == 6:
            break
    for request in unique or [{'start_line': 1, 'end_line': 80}]:
        start = max(1, request.get('start_line', 1))
        end = min(len(lines), request.get('end_line', start + 79))
        for number in range(start, end + 1):
            if number in selected:
                continue
            text = numbered[number - 1]
            if len(text) + 1 > remaining:
                continue
            selected[number] = text
            remaining -= len(text) + 1
    return {**base, 'content': '\n'.join(selected[n] for n in sorted(selected)),
            'included_lines': sorted(selected), 'complete': False,
            'omitted_evidence': 'Only numbered lines shown are supplied. Missing lines may be read again; historical inspection does not mean this worker received them.'}


def note_delivery(runtime, files, observed_lines):
    delivered = {(f['path'], f['hash']): observed_lines(f) for f in files if f.get('hash') and f.get('path')}
    runtime.omitted_context_lines = {key: set(value['lines']) - delivered.get(key, set())
                                     for key, value in runtime.file_observations.items()}
