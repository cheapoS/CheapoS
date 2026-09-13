"""Tiny loopback HTTP fixture: copied records, fail-closed side effects, no Engine/Git."""
import copy
import http.client
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from cheapos.server import LocalServer
from contract import task, TASK_ID, SECRET, private_absent


class Records:
    def __init__(self):
        self.tasks = {TASK_ID: task(), 'interactive': {'id':'interactive'},
                      'unsupported': {'id':'unsupported', 'branch_run': {'schema_version':999}}}
    def get(self, identity):
        if identity not in self.tasks: raise ValueError('Task not found')
        return copy.deepcopy(self.tasks[identity])
    def __getattr__(self, name):
        raise AssertionError('Export attempted store side effect: '+name)


class ReadOnlyEngine:
    def __init__(self): self.store = Records()
    def __getattr__(self, name):
        raise AssertionError('Export attempted engine operation: '+name)


class EndpointAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.engine = ReadOnlyEngine()
        self.server = LocalServer(('127.0.0.1',0), Path(self.temp.name), self.engine)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval':0.001}, daemon=True)
        self.thread.start()
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()
    def request(self, identity, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1',self.server.server_port, timeout=3)
        try:
            conn.request('GET','/api/tasks/'+identity+'/run-report',headers=headers or {})
            response=conn.getresponse(); return response.status,dict(response.getheaders()),response.read()
        finally: conn.close()
    def test_download_repeated_safe_headers_and_no_side_effect(self):
        self.engine.store.tasks[TASK_ID]['title']='東京\r\nX-Evil: '+SECRET
        before=copy.deepcopy(self.engine.store.tasks)
        with patch('subprocess.Popen', side_effect=AssertionError('No Git/process allowed')):
            first=self.request(TASK_ID); second=self.request(TASK_ID)
        status,headers,body=first
        self.assertEqual(status,200); self.assertEqual(first[0],second[0]); self.assertEqual(first[2],second[2])
        self.assertRegex(headers['Content-Type'].lower(),r'text/(markdown|plain).*charset=utf-8')
        self.assertEqual(headers['Content-Disposition'], 'attachment; filename="cheapos-run-'+TASK_ID+'.md"')
        self.assertEqual(headers.get('X-Content-Type-Options'),'nosniff')
        self.assertNotIn('X-Evil',headers); self.assertNotIn(SECRET,str(headers))
        self.assertIn('東京',body.decode('utf-8'))
        self.assertEqual(before,self.engine.store.tasks)
    def test_unknown_interactive_unsupported_and_origin(self):
        for identity in ('missing','interactive','unsupported'):
            with self.subTest(identity=identity):
                status,_,body=self.request(identity); self.assertTrue(400<=status<500); self.assertLess(len(body),4096)
        self.assertEqual(self.request(TASK_ID,{'Origin':'https://untrusted.invalid'})[0],403)
        self.assertEqual(self.request(TASK_ID,{'Sec-Fetch-Site':'cross-site'})[0],403)
