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


KNOWN_WEIGHTS = {
    'test_commits': 120,
    'test_commit_reconciliation': 40,
    'test_commit_recovery': 40,
    'test_branch_completion': 98,
    'test_branch_end_to_end': 97,
    'test_branch_final': 84,
    'test_branch_commits': 75,
    'test_branch_execution': 63,
    'test_branch_recovery': 60,
    'test_branch_merge': 57,
    'test_branch_workspace': 35,
    'test_http': 31,
    'test_branch_commit_controller': 30,
    'test_benchmark': 28,
    'test_model_pool': 24,
    'test_routing': 22,
    'test_compact_edits': 22,
    'test_answer_recovery': 19,
    'test_branch_planning_http': 17,
    'test_checkpoint_boundaries': 15,
    'test_branch_evidence': 15,
    'test_permissions': 14,
    'test_starter_scope': 13,
    'test_branch_http': 13,
    'test_project_permissions': 13,
    'test_chat': 12,
    'test_branch_start': 12,
    'test_engine': 12,
    'test_output_recovery': 11,
    'test_samples': 10,
    'test_branch_review': 10,
    'test_branch_reprepare': 10,
}


def module_priority(module):
    name = module.split('.')[-1]
    return KNOWN_WEIGHTS.get(name, 1)


def run_modules(modules, args, patterns, runner):
    live = set()
    lock = threading.Lock()
    stopping = threading.Event()
    reports = []
    ordered = sorted(modules, key=module_priority, reverse=True)
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
            futures = [pool.submit(run, index, module) for index, module in enumerate(ordered)]
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
