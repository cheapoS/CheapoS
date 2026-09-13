#!/usr/bin/env python3
"""Standard-library test runner with opt-in local timing reports."""
import argparse
import json
import platform
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TimedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timings = []

    def startTest(self, test):
        self.started = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        self.timings.append({'test': test.id(), 'seconds': time.perf_counter() - self.started})
        super().stopTest(test)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default=str(ROOT / 'tests'))
    parser.add_argument('--pattern', default='test_*.py')
    parser.add_argument('--timings', action='store_true')
    parser.add_argument('--json', type=Path, help='Explicit local JSON report destination')
    args = parser.parse_args(argv)
    suite = unittest.defaultTestLoader.discover(args.directory, pattern=args.pattern)
    started = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=2, resultclass=TimedResult).run(suite)
    elapsed = time.perf_counter() - started
    report = {'tests': result.testsRun, 'successful': result.wasSuccessful(), 'failures': len(result.failures),
              'errors': len(result.errors), 'skipped': len(result.skipped), 'expected_failures': len(result.expectedFailures),
              'unexpected_successes': len(result.unexpectedSuccesses), 'seconds': elapsed,
              'environment': {'python': platform.python_version(), 'os': platform.system(), 'machine': platform.machine()},
              'timings': sorted(result.timings, key=lambda item: item['seconds'], reverse=True)}
    if args.timings:
        print(f"\n{report['tests']} tests · {'PASS' if report['successful'] else 'FAIL'} · {elapsed:.3f}s")
        print('Slowest tests (including per-test setup and teardown):')
        for item in report['timings'][:10]:
            print(f"{item['seconds']:8.3f}s  {item['test']}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
