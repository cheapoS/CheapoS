import unittest
from cheapos.benchmark import run


class BenchmarkTests(unittest.TestCase):
    def test_pinned_controller_benchmarks(self):
        result=run()
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['fixtures']),7)
        self.assertEqual({f['kind'] for f in result['fixtures']},{'readme','utility','bug_fix','public_link','failed_check_repair','reviewer_revision','commit_conflict'})
        self.assertEqual(result['fixtures'][0]['outcome'],'human_accepted')
        self.assertTrue(all(f['cost']['accounted']==0 for f in result['fixtures']))
