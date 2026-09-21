#!/usr/bin/env python3
"""Run cheapoS on this computer using only Python's standard library."""

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from cheapos.engine import Engine
from cheapos.server import LocalServer
from cheapos.launch import default_data_directory


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
        raise ValueError("This data directory is already in use by another cheapoS server") from None
    return handle


def main():
    parser = argparse.ArgumentParser(description="Run cheapoS locally. No account required.")
    parser.add_argument("--port", type=int, default=5173, help="Local port (default: 5173)")
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser automatically")
    parser.add_argument("--data-dir", type=Path, default=default_data_directory(__file__), help="Local task storage directory (source: .cheapos; packaged: per-user application data)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if not (APP_DIRECTORY / "index.html").is_file():
        parser.error(f"cheapoS files are missing from {APP_DIRECTORY}")

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
                print(f"cheapoS is already running at {url}", flush=True)
                if not args.no_open:
                    webbrowser.open(url)
                return 0
        except (OSError, URLError, ValueError):
            pass
        print(f"Could not start cheapoS on port {args.port}: {error}", file=sys.stderr)
        print("Try another port: python3 run.py --port 5174", file=sys.stderr)
        return 1

    try:
        data_lock = lock_data(args.data_dir.expanduser().resolve())
        started = time.monotonic()
        server.engine = Engine(args.data_dir.expanduser())
        server.data_lock = data_lock
        loaded = time.monotonic()
        # Gateway startup is asynchronous; local tasks and saved patches remain accessible.
        server.engine.gateway.startup()
        server.engine.startup.start(automatic=True)
        server.engine.restore_route_waits()
        server.engine.storage_maintenance.start()
        print(f'cheapoS startup: saved work loaded in {loaded-started:.2f}s; '
              f'continuations restored in {time.monotonic()-loaded:.2f}s.', flush=True)
    except (OSError, ValueError) as error:
        server.server_close()
        print(str(error), file=sys.stderr)
        return 1
    print(f"cheapoS is running at {url}", flush=True)
    print("Local only. No sign-in required. Press Ctrl+C to stop.", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\ncheapoS stopped.", flush=True)
    finally:
        server.engine.shutdown()
        server.server_close()
        try:
            data_lock.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
