"""Operator-selected command isolation. No model tool may select a backend.

Bubblewrap is deliberately offline and Linux-only. Unsupported/missing namespace
features fail in bwrap; never retry the command on the host.
"""
import hashlib
import os
from pathlib import Path
import platform
import shutil
import stat

VERSION = 1
BWRAP = '/usr/bin/bwrap'
SYSTEM = ('/usr', '/bin', '/sbin', '/lib', '/lib64')
PATH = '/usr/bin:/bin'


def select(value):
    if not isinstance(value, str) or value not in {'host', 'bubblewrap'}:
        raise ValueError('Command backend must be host or bubblewrap')
    return value


def captured(task):
    # Old tasks keep their original host semantics, regardless of new defaults.
    return select(task.get('command_backend', 'host'))


def available(backend):
    if select(backend) == 'host':
        return
    if platform.system() != 'Linux':
        raise ValueError('Bubblewrap command isolation requires Linux; host fallback is disabled')
    binary = Path(BWRAP)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError('Bubblewrap is unavailable at /usr/bin/bwrap; host fallback is disabled')
    mode = binary.stat()
    if mode.st_uid != 0 or mode.st_mode & (stat.S_IWGRP | stat.S_IWOTH | stat.S_ISUID | stat.S_ISGID):
        raise ValueError('Bubblewrap must be root-owned, non-setuid and not group/world writable')


def descriptor(backend):
    return {'backend': select(backend), 'policy_version': VERSION,
            'network': 'none' if backend == 'bubblewrap' else 'host',
            'filesystem': 'task-write-system-read' if backend == 'bubblewrap' else 'host'}


def environment(root, cwd):
    paths = [cwd / 'tests', cwd, root / 'tests', root]
    return {'PATH': PATH, 'HOME': '/home/worker', 'TMPDIR': '/tmp',
            'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
            'PYTHONPATH': ':'.join(dict.fromkeys(str(p) for p in paths if p.is_dir())),
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1',
            'CI': '1', 'NO_COLOR': '1', 'GIT_TERMINAL_PROMPT': '0',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}


def executable(value, root, cwd):
    """Resolve using the sandbox PATH, never the server's user toolchain PATH."""
    candidate = (str(cwd / value) if '/' in value and not Path(value).is_absolute()
                 else value if Path(value).is_absolute() else shutil.which(value, path=PATH))
    if not candidate:
        return None
    path = Path(candidate)
    resolved = path.resolve()
    visible = any(resolved.is_relative_to(Path(p).resolve()) for p in SYSTEM if Path(p).exists()) or resolved.is_relative_to(root)
    return str(path) if visible and path.is_file() and os.access(path, os.X_OK) else None


def identity(backend, root, cwd):
    if select(backend) == 'host':
        return None  # Preserve legacy host check identities.
    available(backend)
    binary = Path(BWRAP)
    return {**descriptor(backend), 'launcher_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
            'kernel': platform.release(), 'environment': environment(root, cwd)}


def validate_workspace(root):
    # Do not mount a task over the system runtime or ephemeral sandbox paths.
    if root in {Path('/'), Path('/tmp')} or any(root == Path(p) or root.is_relative_to(p) or Path(p).is_relative_to(root)
                               for p in (*SYSTEM, '/proc', '/dev', '/home/worker')):
        raise ValueError('Task workspace overlaps a reserved isolation mount')
    # A socket or hard-linked file can bridge the writable mount to host state.
    # Do not follow symlinks: their destinations are interpreted in the namespace.
    def failed(error):
        raise error
    for parent, dirs, files in os.walk(root, followlinks=False, onerror=failed):
        for name in dirs + files:
            info = (Path(parent) / name).lstat()
            if stat.S_ISREG(info.st_mode):
                if info.st_nlink > 1:
                    raise ValueError('Isolation refuses hard-linked task files')
            elif not (stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)):
                raise ValueError('Isolation refuses task sockets, devices and FIFOs')


def launch(backend, argv, root, cwd, host_env):
    select(backend)
    if backend == 'host':
        return argv, host_env
    available(backend)
    validate_workspace(root)
    env = environment(root, cwd)
    command = [BWRAP, '--unshare-user', '--unshare-pid', '--unshare-net',
               '--unshare-ipc', '--unshare-uts', '--die-with-parent', '--new-session',
               '--cap-drop', 'ALL', '--disable-userns', '--clearenv']
    for mount in SYSTEM:
        if Path(mount).exists():
            command += ['--ro-bind', mount, mount]
    command += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
                '--dir', '/home', '--tmpfs', '/home/worker']
    # Only loader configuration is exposed, not /etc credentials or host sockets.
    for name in ('/etc/ld.so.cache', '/etc/ld.so.conf'):
        if Path(name).is_file():
            command += ['--ro-bind', name, name]
    command += ['--bind', str(root), str(root)]
    marker = root / '.git'
    if marker.is_symlink():
        raise ValueError('Isolation refuses a symlinked Git marker')
    if marker.is_dir():
        command += ['--ro-bind', str(marker), str(marker)]
    elif marker.exists():
        command += ['--ro-bind', '/dev/null', str(marker)]
    for key, value in env.items():
        command += ['--setenv', key, value]
    command += ['--chdir', str(cwd), '--', *argv]
    return command, {'PATH': PATH, 'LANG': 'C.UTF-8'}


def require_host_preview(task):
    if captured(task) != 'host':
        raise ValueError('Previews are unavailable for isolated tasks; host fallback is disabled')
