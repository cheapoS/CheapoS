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
            self.assertEqual(clean.returncode,0)
