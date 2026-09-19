"""Storage and process arguments shared by source and packaged launchers."""
import os
import sys
from pathlib import Path


def default_data_directory(entrypoint):
    entrypoint = Path(entrypoint).resolve()
    packaged = getattr(sys, 'frozen', False) or any(
        parent.name == 'Contents' and parent.parent.suffix == '.app'
        for parent in entrypoint.parents)
    if not packaged:
        # Preserve existing source installations and explicit --data-dir use.
        return entrypoint.parent / '.cheapos'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'cheapoS'
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'cheapoS'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'cheapoS'


def restart_arguments():
    # A frozen executable is already the entrypoint; Python needs the script too.
    args = sys.argv[1:] if getattr(sys, 'frozen', False) else sys.argv
    return [sys.executable, *args]
