#!/usr/bin/env python3
"""Serve a disposable, completed scripted demo for repository screenshots."""

import argparse
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cheapos.engine import Engine
from cheapos.server import LocalServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5186)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    with tempfile.TemporaryDirectory(prefix='cheapos-readme-') as directory:
        engine = Engine(Path(directory), fixture_delay=0)
        server = None
        try:
            # Do not invoke model discovery, greetings, or gateway startup.
            engine.startup.configure({'enabled': False, 'allow_cloud': False})
            engine.gateway.settings['auto_start'] = False
            server = LocalServer(('127.0.0.1', args.port), ROOT / 'dist', engine)
            task = engine.create_demo()
            engine.start(task['id'])
            worker = engine.runtimes[task['id']].thread
            worker.join(30)
            if worker.is_alive():
                raise RuntimeError('The scripted demo did not finish in 30 seconds')
            result = engine.store.get(task['id'])
            if result['status'] != 'approved':
                raise RuntimeError(f'Demo stopped at {result["status"]}: {result.get("error")}')
            print(f'Open http://127.0.0.1:{args.port}/ and select Local demo in the sidebar.', flush=True)
            print('Scripted models; real fixture edits and checks. Ctrl+C removes the temporary task data.', flush=True)
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            engine.shutdown()
            for runtime in engine.runtimes.values():
                if runtime.thread:
                    runtime.thread.join(5)
            if server:
                server.server_close()


if __name__ == '__main__':
    main()
