import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RUNNER=Path(__file__).resolve().parents[1]/'scripts/dev_tests.py'


class DeveloperRunnerTests(unittest.TestCase):
    def test_failures_subtests_skips_expected_failures_and_fixture_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'test_sample.py').write_text('''import unittest, time
class Sample(unittest.TestCase):
    def setUp(self): time.sleep(.01)
    def tearDown(self): time.sleep(.01)
    def test_ok(self): pass
    def test_bad(self): self.fail('deliberate failure')
    @unittest.skip('fixture skip')
    def test_skip(self): pass
    @unittest.expectedFailure
    def test_expected(self): self.fail('expected')
    def test_subtest(self):
        with self.subTest(value=1): self.assertEqual(1,2)
''')
            report=root/'report.json'
            result=subprocess.run([sys.executable,'-B',str(RUNNER),'--directory',str(root),'--pattern','test_sample.py','--timings','--json',str(report)],capture_output=True,text=True)
            data=json.loads(report.read_text())
            self.assertEqual(result.returncode,1)
            self.assertEqual((data['tests'],data['failures'],data['skipped'],data['expected_failures']),(5,2,1,1))
            self.assertIn('deliberate failure',result.stderr)
            self.assertIn('value=1',result.stderr)
            self.assertGreaterEqual(data['seconds'],.08)
            self.assertLessEqual(sum(item['seconds'] for item in data['timings']),data['seconds'])
            self.assertIn('Slowest tests',result.stdout)
            clean=subprocess.run([sys.executable,'-B',str(RUNNER),'--directory',str(root),'--pattern','missing*.py'],capture_output=True)
            self.assertEqual(clean.returncode,1)
            self.assertIn(b'No tests discovered',clean.stderr)

    def test_empty_discovery_and_empty_module_fail_with_truthful_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'test_empty.py').write_text('# No test cases yet\n')
            for pattern in ('missing*.py','test_empty.py'):
                report=root/'report.json'
                result=subprocess.run([sys.executable,'-B',str(RUNNER),'--directory',str(root),'--pattern',pattern,'--timings','--json',str(report)],capture_output=True,text=True)
                self.assertEqual(result.returncode,1)
                self.assertIn('No tests discovered',result.stderr)
                self.assertIn('0 tests · FAIL',result.stdout)
                data=json.loads(report.read_text())
                self.assertEqual(data['tests'],0)
                self.assertFalse(data['successful'])


    def test_fast_selection_catches_relevant_failure_and_full_includes_integration(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'test_titles.py').write_text("import unittest\nclass T(unittest.TestCase):\n def test_failure(self): self.fail('fast failure')\n")
            (root/'test_integration.py').write_text("import unittest\nclass T(unittest.TestCase):\n def test_failure(self): self.fail('integration failure')\n")
            for suite,count in [('fast',1),('full',2)]:
                report=root/(suite+'.json')
                result=subprocess.run([sys.executable,'-B',str(RUNNER),'--directory',str(root),'--suite',suite,'--json',str(report)],capture_output=True)
                self.assertEqual(result.returncode,1)
                self.assertEqual(json.loads(report.read_text())['tests'],count)
