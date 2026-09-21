"""Small pure-data evidence cases: no agent/Git workflows or real-time waits."""
import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from cheapos import job_evidence as jobs
from cheapos.lifetime_usage import LifetimeUsage
from cheapos.metrics import record_usage, ExactFloat
from tests.test_lifetime_usage import record

class JobEvidenceTests(unittest.TestCase):
    def task(self):
        t=dict(id='chat',branch_run={'id':'run','status':'draft'},request_metrics=[],events=[])
        with patch.object(jobs, 'stamp', return_value='2020-01-01T00:00:00+00:00'):
            jobs.prepare(t)
        return t

    def test_clock_ready_acceptance_and_no_double_count(self):
        t=self.task();j={};jobs.observe(j,t,'2020-01-01T00:00:00+00:00')
        r=t['branch_run'];r.update(status='running',authorization_ref='auth')
        jobs.observe(j,t,'2020-01-01T00:00:01+00:00')
        t['route_wait']={"retry_at":100};jobs.observe(j,t,'2020-01-01T00:00:11+00:00')
        t.pop('route_wait');r['status']='paused';jobs.observe(j,t,'2020-01-01T00:00:21+00:00')
        r.update(status='ready_for_merge',readiness={'id':'candidate'},final_evidence=dict(candidate_id='candidate',review_candidate_id='candidate',checks_passed=True,review_approved=True,acceptance_satisfied=True))
        jobs.observe(j,t,'2020-01-01T00:00:31+00:00')
        r.update(status='merged',merge_receipt={'id':'merge'},merge_authorization={'contract':{'readiness_id':'candidate','operation':{'id':'merge'}}})
        jobs.observe(j,t,'2020-01-02T00:00:00+00:00')
        x=j[t['coding_job_id']];self.assertEqual([x[k] for k in ('active_ms','provider_wait_ms','operator_wait_ms')],[10000,10000,10000]);self.assertEqual(x['state'],'accepted')
        jobs.observe(j,t,'2020-01-02T00:01:00+00:00');self.assertEqual(len(j),1)
        next_task=copy.deepcopy(t);next_task['branch_run']={'id':'next','status':'draft'};jobs.prepare(next_task,t)
        self.assertNotEqual(t['coding_job_id'],next_task['coding_job_id'])

    def test_old_approval_cannot_accept_different_candidate(self):
        t=self.task();t['branch_run'].update(status='merged',readiness={'id':'new'},final_evidence={'candidate_id':'old','review_candidate_id':'old','checks_passed':True,'review_approved':True,'acceptance_satisfied':True},merge_receipt={'id':'x'})
        j={};jobs.observe(j,t);self.assertIsNone(j[t['coding_job_id']]['acceptance_id']);self.assertEqual(j[t['coding_job_id']]['state'],'stopped')

    def test_journal_survives_request_eviction_cleanup_and_restart(self):
        t=self.task();rid=t['coding_job_id'];t['request_metrics']=[record('request',job_id=rid,reported_cost_exact='0.00000001',reported_currency='USD',status='failed')]
        with tempfile.TemporaryDirectory() as d:
            ledger=LifetimeUsage(d);ledger.ingest(t)
            t['request_metrics']=[];t['branch_run'].update(authorization_ref='a',status='running');ledger.ingest(t)
            reloaded=LifetimeUsage(d);x=reloaded.job_export()[0]
            self.assertEqual(x['requests'][0]['reported_cost_exact'],'0.00000001');self.assertFalse(x['timing_complete']);self.assertEqual(x['job_id'],rid)

    def test_structured_rescue_approvals_and_ambiguous_guidance(self):
        t=self.task();t['branch_run']['authorization_ref']='a';j={};jobs.observe(j,t,'2020-01-01T00:00:01+00:00')
        for n,kind in enumerate(['check_approval','branch_merged','job_resume','operator_revision','user']):
            t['events'].append(dict(id=n,time='2020-01-01T00:00:02+00:00',kind=kind,detail='PRIVATE'))
        jobs.observe(j,t,'2020-01-01T00:00:03+00:00');jobs.observe(j,t,'2020-01-01T00:00:04+00:00')
        x=j[t['coding_job_id']];self.assertEqual((x['approvals'],x['rescue_actions'],x['unclassified_actions']),(3,2,3));self.assertNotIn('PRIVATE',json.dumps(jobs.export(j,[])))

    def test_decimal_cost_not_reservation_or_classification(self):
        value=json.loads('{"cost":0.0000000000000000001234}',parse_float=ExactFloat)
        r={};record_usage(r,value,False);self.assertEqual(r['reported_cost_exact'],'0.0000000000000000001234')
        r={};record_usage(r,{},False);self.assertNotIn('reported_cost_exact',r)

class JobSyncTests(unittest.TestCase):
    def manager(self,directory):
        from cheapos.club import ClubManager
        from unittest.mock import Mock
        import hashlib
        m=ClubManager(directory,credentials=Mock());m.state.update(identity={'handle':'a'},pairing_id='pair',sync_enabled=True,share_jobs=True,jobs_since='2019-01-01T00:00:00+00:00')
        m._signed=lambda message:{'payload':json.dumps(message)}
        def reply(envelope):
            data=json.loads(envelope['payload'])
            if data['action']=='status':return {'capabilities':['accepted_jobs_v1']}
            return dict(status='accepted',sequence=data['sequence'],hash=hashlib.sha256(envelope['payload'].encode()).hexdigest(),job_pages_accepted=1)
        m._request=reply
        return m

    def test_pages_replay_outcome_only_update_and_old_server(self):
        from cheapos.club_jobs import sync_jobs
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as d:
            m=self.manager(d);t=JobEvidenceTests().task();j={};jobs.observe(j,t,'2020-01-01T00:00:00+00:00')
            rows=[dict(request_id=str(n),job_id=t['coding_job_id'],status='failed',reported_cost_exact='0',reported_currency='USD') for n in range(23)]
            m.state['attempts_sent']={str(n):'accepted' for n in range(23)}
            ledger=Mock();ledger.job_export.side_effect=lambda:jobs.export(j,rows)
            self.assertEqual(sync_jobs(m,ledger),1);self.assertEqual(m.state['job_upload']['index'],1)
            # Simulate restart with the durable snapshot between pages.
            clone=self.manager(d);self.assertEqual(sync_jobs(clone,ledger),1);self.assertIsNone(clone.state['job_upload']);self.assertEqual(sync_jobs(clone,ledger),0)
            j[t['coding_job_id']]['state']='stopped';self.assertEqual(sync_jobs(clone,ledger),1)
            clone.state['job_upload']=None;clone._call=lambda *a,**kw:{'capabilities':[]};self.assertEqual(sync_jobs(clone,ledger),0)
            self.assertIn('waiting',clone.state['jobs_message'])

    def test_missing_ack_keeps_outbox_and_consent_boundary(self):
        from cheapos.club_jobs import sync_jobs
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as d:
            m=self.manager(d);t=JobEvidenceTests().task();j={};jobs.observe(j,t,'2020-01-01T00:00:00+00:00')
            ledger=Mock();ledger.job_export.return_value=jobs.export(j,[])
            m.state['jobs_since']='2021-01-01T00:00:00+00:00';self.assertEqual(sync_jobs(m,ledger),0)
            m.state['jobs_since']='2019-01-01T00:00:00+00:00';original=m._request
            m._request=lambda e:{k:v for k,v in original(e).items() if k!='job_pages_accepted'}
            with self.assertRaisesRegex(ValueError,'acknowledge'):sync_jobs(m,ledger)
            self.assertIsNotNone(m.state['pending']);self.assertEqual(m.state['sequence'],0)
