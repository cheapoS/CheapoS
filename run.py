#!/usr/bin/env python3
"""Run CheapOS on this computer using only Python's standard library."""

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from cheapos.engine import Engine
from cheapos.server import LocalServer


APP_DIRECTORY = Path(__file__).resolve().parent / "dist"
def lock_data(directory):
    """Prevent two processes from running tasks against the same saved work."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = (directory / "server.lock").open("a+")
    try:
        if sys.platform == "win32":
            import msvcrt
            handle.seek(0)
            handle.write("0")
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise ValueError("This data directory is already in use by another CheapOS server") from None
    return handle


def main():
    parser = argparse.ArgumentParser(description="Run CheapOS locally. No account required.")
    parser.add_argument("--port", type=int, default=5173, help="Local port (default: 5173)")
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser automatically")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent / ".cheapos", help="Local task storage directory")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if not (APP_DIRECTORY / "index.html").is_file():
        parser.error(f"CheapOS files are missing from {APP_DIRECTORY}")

    url = f"http://127.0.0.1:{args.port}/"
    # Bind first: a second launch must not mark an active server's tasks interrupted.
    try:
        server = LocalServer(("127.0.0.1", args.port), APP_DIRECTORY, None)
    except OSError as error:
        # A second launch can reuse an already-running copy of this application.
        try:
            with urlopen(url + "api/bootstrap", timeout=2) as response:
                existing = json.loads(response.read(1_000_000))
            if existing.get("app") == "CheapOS":
                print(f"CheapOS is already running at {url}", flush=True)
                if not args.no_open:
                    webbrowser.open(url)
                return 0
        except (OSError, URLError, ValueError):
            pass
        print(f"Could not start CheapOS on port {args.port}: {error}", file=sys.stderr)
        print("Try another port: python3 run.py --port 5174", file=sys.stderr)
        return 1

    try:
        data_lock = lock_data(args.data_dir.expanduser().resolve())
        server.engine = Engine(args.data_dir.expanduser())
        # Gateway startup is asynchronous; local tasks and saved patches remain accessible.
        server.engine.gateway.startup()
    except (OSError, ValueError) as error:
        server.server_close()
        print(str(error), file=sys.stderr)
        return 1
    print(f"CheapOS is running at {url}", flush=True)
    print("Local only. No sign-in required. Press Ctrl+C to stop.", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCheapOS stopped.", flush=True)
    finally:
        server.engine.shutdown()
        server.server_close()
        data_lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
