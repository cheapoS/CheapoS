"""Frozen text versions outside the editable task copy and JSON task record."""
import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path


# Same per-file boundary as committed workspace snapshots. Aggregate evidence
# is stored on disk, not passed to a model or copied on every task save.
MAX_BLOB_BYTES = 2_000_000


def _path(workspace, reference):
    if (not isinstance(reference, dict) or set(reference) != {'sha256', 'bytes'}
            or not isinstance(reference['sha256'], str)
            or not re.fullmatch(r'[a-f0-9]{64}', reference['sha256'])
            or type(reference['bytes']) is not int
            or not 0 <= reference['bytes'] <= MAX_BLOB_BYTES):
        raise ValueError('Invalid captured merge version reference')
    root = Path(workspace).absolute().parent / 'merge-evidence'
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise ValueError('Captured merge evidence cannot use symlinks')
    return root / reference['sha256']


def read(workspace, reference):
    path = _path(workspace, reference)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != reference['bytes']:
                raise ValueError('Captured merge version size changed')
            data = stream.read(MAX_BLOB_BYTES + 1)
    except OSError as error:
        raise ValueError('Captured merge version is unavailable; saved work is unchanged') from error
    if len(data) != reference['bytes'] or hashlib.sha256(data).hexdigest() != reference['sha256']:
        raise ValueError('Captured merge version changed; saved work is unchanged')
    return data


def retain(workspace, data):
    reference = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    path = _path(workspace, reference)
    path.parent.mkdir(mode=0o700, exist_ok=True)
    if path.exists() or path.is_symlink():
        read(workspace, reference)
        return reference
    fd, temporary = tempfile.mkstemp(prefix='.capture-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return reference
