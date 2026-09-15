import unittest
from cheapos.handoff_context import file_excerpt

class HandoffContextTests(unittest.TestCase):
    def test_small_file_is_whole_despite_last_narrow_read(self):
        data='\n'.join('line' for _ in range(98)).encode()
        result=file_excerpt('index.html',data,[{'start_line':10,'end_line':20}],12000)
        self.assertTrue(result['complete'])
        self.assertIn('59: line',result['content'])
        self.assertEqual(result['end_line'],98)

    def test_large_file_retains_multiple_regions_and_marks_omissions(self):
        data='\n'.join('x'*100 for _ in range(98)).encode()
        result=file_excerpt('index.html',data,[{'start_line':10,'end_line':20},{'start_line':59,'end_line':62}],2000)
        self.assertFalse(result['complete'])
        self.assertIn('10: ',result['content'])
        self.assertIn('59: ',result['content'])
        self.assertIn('62: ',result['content'])
        self.assertLessEqual(len(result['content']),2000)
        self.assertIn('may be read again',result['omitted_evidence'])

    def test_changed_files_have_new_identity_and_no_invented_lines(self):
        before=file_excerpt('x',b'old',[],100)
        after=file_excerpt('x',b'new',[],100)
        self.assertNotEqual(before['hash'],after['hash'])
        self.assertEqual(after['content'],'1: new')
