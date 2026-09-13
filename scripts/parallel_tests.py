"""Process-isolated module execution for the developer test runner."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def cases(suite):
    for entry in suite:
        if hasattr(entry, '__iter__'):
            yield from cases(entry)
        else:
            yield entry


def run_modules(modules, args, patterns, runner):
    live = set()
    lock = threading.Lock()
    stopping = threading.Event()
    reports = []
    with tempfile.TemporaryDirectory(prefix='cheapos-tests-') as directory:
        def run(index, module):
            report_path = Path(directory) / (str(index) + '.json')
            command = [sys.executable, '-B', str(runner), '--directory', args.directory,
                       '--jobs', '1', '--worker-module', module, '--json', str(report_path)]
            for pattern in patterns:
                command.extend(['--pattern', pattern])
            with lock:
                if stopping.is_set():
                    return None
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           text=True, start_new_session=os.name != 'nt')
                live.add(process)
            output, errors = process.communicate()
            with lock:
                live.discard(process)
            try:
                report = json.loads(report_path.read_text())
                if process.returncode and report.get('successful'):
                    raise ValueError('Worker exited unsuccessfully')
            except (OSError, ValueError):
                report = dict(tests=0, failures=0, errors=1, skipped=0, expected_failures=0,
                              unexpected_successes=0, successful=False, seconds=0, timings=[])
                errors += '\nWorker failed to produce a valid result: ' + module + '\n'
            return module, report, output, errors

        pool = ThreadPoolExecutor(max_workers=args.jobs)
        try:
            futures = [pool.submit(run, index, module) for index, module in enumerate(modules)]
            for future in as_completed(futures):
                result = future.result()
                if result is None:
                    continue
                module, report, output, errors = result
                reports.append(report)
                print(f"{module}: {report['tests']} tests · {'PASS' if report['successful'] else 'FAIL'} · {report['seconds']:.3f}s", flush=True)
                if not report['successful']:
                    print(output, end='')
                    print(errors, end='', file=sys.stderr)
        except BaseException:
            stopping.set()
            with lock:
                processes = list(live)
            for process in processes:
                try:
                    if os.name == 'nt': process.terminate()
                    else: os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            for process in processes:
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    if os.name == 'nt': process.kill()
                    else:
                        try: os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError: pass
            raise
        finally:
            pool.shutdown(wait=True)
    return reports
