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

    def test_parallel_modules_preserve_results_and_deduplicate_patterns(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'test_good.py').write_text("import unittest\nclass T(unittest.TestCase):\n def test_ok(self): pass\n @unittest.skip('fixture')\n def test_skip(self): pass\n")
            (root/'test_bad.py').write_text("import unittest\nclass T(unittest.TestCase):\n def test_failure(self): self.fail('parallel failure')\n @unittest.expectedFailure\n def test_expected(self): self.fail('expected')\n")
            totals=[]
            for jobs in (1,2):
                report=root/f'report-{jobs}.json'
                result=subprocess.run([sys.executable,'-B',str(RUNNER),'--directory',str(root),'--pattern','test_*.py','--pattern','test_good.py','--jobs',str(jobs),'--json',str(report)],capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode,1)
                self.assertIn('parallel failure',result.stderr)
                data=json.loads(report.read_text())
                totals.append(tuple(data[key] for key in ('tests','failures','errors','skipped','expected_failures')))
            self.assertEqual(totals,[(4,1,0,1,1)]*2)

    def test_parallel_workers_overlap_and_keep_module_fixtures_together(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,other in [('one','two'),('two','one')]:
                (root/f'test_{name}.py').write_text(f"""import os,time,unittest
from pathlib import Path
root=Path(__file__).parent
value=None
def setUpModule():
 global value
 value=os.getpid()
 (root/'{name}.pid').write_text(str(value))
 deadline=time.monotonic()+5
 while not (root/'{other}.pid').exists():
  if time.monotonic()>deadline:raise AssertionError('workers did not overlap')
  time.sleep(.01)
class T(unittest.TestCase):
 def test_module_fixture(self):self.assertEqual(value,os.getpid())
 def test_another(self):self.assertEqual(value,os.getpid())
""")
            report=root/'report.json'
            result=subprocess.run([sys.executable,'-B',str(RUNNER),'--directory',str(root),'--suite','full','--jobs','2','--json',str(report)],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(report.read_text())['tests'],4)
            self.assertNotEqual((root/'one.pid').read_text(),(root/'two.pid').read_text())

    def test_worker_crash_and_import_error_cannot_report_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'test_good.py').write_text("import unittest\nclass T(unittest.TestCase):\n def test_ok(self): pass\n")
            bad=root/'test_bad.py'
            for content in ("import unittest,os\nclass T(unittest.TestCase):\n def test_exit(self):os._exit(7)\n", "raise RuntimeError('broken import')\n"):
                bad.write_text(content)
                report=root/'report.json'
                result=subprocess.run([sys.executable,'-B',str(RUNNER),'--directory',str(root),'--jobs','2','--json',str(report)],capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode,1)
                self.assertFalse(json.loads(report.read_text())['successful'])
                self.assertGreater(json.loads(report.read_text())['errors'],0)
