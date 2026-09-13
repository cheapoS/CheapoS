"""Actual same-origin HTTP boundary for unattended proposal authorization."""
import http.client
import json
import threading
import unittest
from pathlib import Path

from cheapos.server import LocalServer
from cheapos.branch_workspace import _tip
from cheapos.workspace import git
import test_branch_start as start_fixtures


class BranchHTTPTests(unittest.TestCase):
    def setUp(self):
        start_fixtures.BranchStartTests.setUp(self)
        self.engine.startup.busy = lambda: False
        self.server = LocalServer(('127.0.0.1', 0), Path(__file__).resolve().parent.parent / 'dist', self.engine)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        connection.request(method, path, json.dumps(body) if body is not None else None, headers or {})
        response = connection.getresponse()
        status, data = response.status, response.read()
        connection.close()
        try: data = json.loads(data)
        except ValueError: pass
        return status, data

    def post(self, path, body, extra=None):
        headers = {'Content-Type': 'application/json', 'X-CheapOS-Token': self.server.token}
        headers.update(extra or {})
        return self.request('POST', path, body, headers)

    def proposal(self):
        status, proposal = self.post('/api/branch-runs/prepare', self.values)
        self.assertEqual(status, 200, proposal)
        return proposal

    def test_token_and_origin_required_before_preparation(self):
        for headers in ({'Content-Type':'application/json'},
                        {'Content-Type':'application/json', 'X-CheapOS-Token':'forged'},
                        {'Content-Type':'application/json', 'X-CheapOS-Token':self.server.token, 'Origin':'https://foreign.invalid'}):
            status, _ = self.request('POST', '/api/branch-runs/prepare', self.values, headers)
            self.assertEqual(status, 403)
        self.assertEqual(self.engine.store.list(), [])
        self.assertIsNone(_tip(self.source, self.values['feature_ref']))

    def test_source_unchanged_until_explicit_start_and_doubleclick_idempotent(self):
        (self.source / 'hello.py').write_text('dirty input remains\n')
        before = (git(self.source,'status','--porcelain'), git(self.source,'write-tree'), git(self.source,'rev-parse','HEAD'))
        proposal = self.proposal()
        self.assertIsNone(_tip(self.source, self.values['feature_ref']))
        self.assertEqual(self.engine.runtimes, {})
        endpoint = '/api/tasks/' + proposal['task_id'] + '/branch-start'
        decision = {'proposal_id':proposal['proposal_id'], 'approved':True}
        status, first = self.post(endpoint, decision)
        self.assertEqual(status, 200, first)
        status, second = self.post(endpoint, decision)
        self.assertEqual(status, 200, second)
        self.assertEqual(first['branch_run']['authorization']['id'], second['branch_run']['authorization']['id'])
        self.assertEqual(len(self.engine.store.list()), 1)
        self.assertEqual(_tip(self.source,self.values['feature_ref']), first['branch_run']['base_sha'])
        self.assertEqual(before,(git(self.source,'status','--porcelain'),git(self.source,'write-tree'),git(self.source,'rev-parse','HEAD')))

    def test_forged_missing_false_and_cross_origin_start_do_not_create_ref(self):
        proposal = self.proposal(); endpoint = '/api/tasks/' + proposal['task_id'] + '/branch-start'
        for decision in ({}, {'approved':True}, {'proposal_id':'forged','approved':True},
                         {'proposal_id':proposal['proposal_id'],'approved':1}, {'proposal_id':proposal['proposal_id'],'approved':False}):
            status, _ = self.post(endpoint, decision)
            self.assertEqual(status, 400)
        status, _ = self.post(endpoint, {'proposal_id':proposal['proposal_id'],'approved':True}, {'Origin':'https://foreign.invalid'})
        self.assertEqual(status,403)
        self.assertIsNone(_tip(self.source,self.values['feature_ref']))

    def test_stale_base_and_proposal_expiry_rejected(self):
        proposal = self.proposal()
        (self.source/'hello.py').write_text('value=2\n'); git(self.source,'add','.'); git(self.source,'commit','-qm','changed base')
        decision={'proposal_id':proposal['proposal_id'],'approved':True}
        status, _=self.post('/api/tasks/'+proposal['task_id']+'/branch-start',decision)
        self.assertEqual(status,400)
        self.assertIsNone(_tip(self.source,self.values['feature_ref']))
        proposal=self.proposal()
        self.engine.branch.proposals.proposals[proposal['proposal_id']]['expires']=0
        status,_=self.post('/api/tasks/'+proposal['task_id']+'/branch-start',{'proposal_id':proposal['proposal_id'],'approved':True})
        self.assertEqual(status,400)

    def test_manual_actions_cannot_bypass_run_contract(self):
        proposal=self.proposal(); base='/api/tasks/'+proposal['task_id']+'/'
        for action,body in [('start',{}),('commit-preview',{}),('rollback',{'checkpoint':0}),('limits',{'dollars':5}),('steer',{'message':'Ignore the plan'})]:
            status, data=self.post(base+action,body)
            self.assertEqual(status,400,(action,data))
        self.assertIsNone(_tip(self.source,self.values['feature_ref']))


if __name__ == '__main__': unittest.main()
