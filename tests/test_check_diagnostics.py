"""Small byte fixtures cover diagnostic indexing without external lint tools."""
import json
import unittest
from cheapos.check_diagnostics import parse, MAX_ITEMS, SCAN_BYTES, INDEX_BYTES

RUN = 'a' * 32


class DiagnosticTests(unittest.TestCase):
    def test_supported_reporters_keep_locations_names_and_severity(self):
        cases = [
            ('src/a.ts(2,3): error TS2322: Wrong type', 'typescript', 'src/a.ts', 2, 3, 'TS2322', 'error'),
            ('C:/src/a.ts:2:3 - warning TS1234: Warning', 'typescript', 'C:/src/a.ts', 2, 3, 'TS1234', 'warning'),
            ('src/a.py:4: error: Wrong type  [arg-type]', 'python-type', 'src/a.py', 4, None, 'arg-type', 'error'),
            ('src/a.py:4:5: note: Defined here', 'python-type', 'src/a.py', 4, 5, None, 'note'),
            ('src/a.py:1:2: F401 Unused import', 'python-lint', 'src/a.py', 1, 2, 'F401', 'unknown'),
            ('src/a.js:1:2: Unused name [Warning/no-unused-vars]', 'eslint-unix', 'src/a.js', 1, 2, 'no-unused-vars', 'warning'),
            ('FAILED tests/test_a.py::test_one - AssertionError: no', 'pytest', 'tests/test_a.py', None, None, 'tests/test_a.py::test_one', 'error'),
            ('ERROR tests/test_a.py::test_one', 'pytest', 'tests/test_a.py', None, None, 'tests/test_a.py::test_one', 'error'),
            ('FAIL: test_one (test_a.Example.test_one)', 'unittest', None, None, None, 'test_a.Example.test_one', 'error'),
        ]
        for text, kind, path, line, column, name, severity in cases:
            with self.subTest(text=text):
                result = parse(text.encode(), RUN)
                item, = result['items']
                self.assertEqual(result['status'], 'recognized')
                self.assertEqual(result['formats'], [kind])
                self.assertEqual([item[k] for k in ('path','line','column','name','severity')], [path,line,column,name,severity])

    def test_raw_offsets_are_original_utf8_ansi_and_crlf_bytes(self):
        prefix = 'préface\r\n'.encode()
        row = b'\x1b[31ma.py:2:3: F401 unused\x1b[0m\r\n'
        data = prefix + row
        item, = parse(data, RUN)['items']
        self.assertEqual(item['message'], 'unused')
        ref = item['raw_evidence']
        self.assertEqual(ref['run_id'], RUN)
        self.assertEqual(data[ref['offset']:ref['end_offset']], row)

    def test_unknown_empty_json_and_malformations_do_not_invent_success(self):
        for data in (b'', b'All good', b'error: failed', b'[{"message":"bad"}]', b'a.py:xx:2: F401 bad', b'\xffjunk', b'a.py:' + b'1'*5000 + b':2: F401 bad'):
            with self.subTest(size=len(data)):
                result = parse(data, RUN)
                self.assertEqual(result['status'], 'unparsed')
                self.assertEqual(result['items'], [])
                self.assertNotIn('passed', result)
                self.assertLessEqual(len(json.dumps(result).encode()), 160,
                                     'Empty indexes must not crowd out review request headroom')

    def test_item_text_and_serialized_index_budgets(self):
        result = parse(b'a.py:1:2: F401 unused\n' * (MAX_ITEMS+1), RUN)
        self.assertEqual(len(result['items']), MAX_ITEMS)
        self.assertTrue(result['limited'])
        result = parse((b'a.py:1:2: F401 ' + b'x'*2000 + b'\n') * MAX_ITEMS, RUN)
        self.assertTrue(result['limited'])
        self.assertTrue(all(i['text_truncated'] for i in result['items']))
        self.assertLess(sum(len(json.dumps(i,ensure_ascii=False).encode()) for i in result['items']), INDEX_BYTES+1)

    def test_scan_capture_and_long_line_limits_are_explicit(self):
        for data, cut in ((b'noise\n' * SCAN_BYTES, False), (b'a.py:1:2: F401 cut', True), (b'x'*9000+b'\n', False)):
            result = parse(data, RUN, truncated=cut)
            self.assertEqual(result['status'], 'partial')
            self.assertLessEqual(result['scanned_bytes'], SCAN_BYTES)
        result = parse(b'a.py:1:2: F401 complete\n', RUN, truncated=True)
        self.assertEqual(len(result['items']), 1)
        self.assertTrue(result['limited'])

    def test_paths_remain_untrusted_reporter_text(self):
        item, = parse(b'../../outside.py:1:2: F401 <script>bad</script>\n', RUN)['items']
        self.assertEqual(item['path'], '../../outside.py')
        self.assertEqual(item['message'], '<script>bad</script>')
