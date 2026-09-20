"""Small deterministic protocol checks; no network, models or keychain calls."""
import hashlib
import json
import tempfile
import unittest
from unittest.mock import Mock
from cheapos.club import ClubManager

class ClubTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.club=ClubManager(self.temp.name,credentials=Mock())
        self.club.state.update(identity={'handle':'alice'},pairing_id='pair')
        self.club._signed=lambda message: {'payload':json.dumps(message,sort_keys=True),'signature':'test'}
        self.club.start_background=lambda lifetime: None
        self.rows=[];self.ledger=Mock();self.ledger.raw_requests.side_effect=lambda:self.rows
        self.club.lifetime=self.ledger
        self.sent=[]
        def accept(envelope):
            self.sent.append(envelope)
            message=json.loads(envelope['payload'])
            return {'status':'accepted','sequence':message['sequence'],'hash':hashlib.sha256(envelope['payload'].encode()).hexdigest()}
        self.accept=accept;self.club._request=accept

    def row(self,id='new',tokens=12,role='worker'):
        return {'request_id':id,'date':'2026-09-15','reconciled':True,'input_tokens':tokens,'output_tokens':3,'category':'local','club_category':'unknown','role':role}

    def test_opt_in_excludes_existing_usage_and_duplicate_ticks(self):
        self.rows.append(self.row('old'));self.club.set_sync(True)
        self.rows.append(self.row());self.club.sync_now(self.ledger)
        event=json.loads(self.sent[-1]['payload'])['events'][0]
        self.assertEqual(event['input_tokens'],12)
        self.assertEqual(event.get('role'),'worker')
        before=len(self.sent);self.club.sync_now(self.ledger);self.assertEqual(len(self.sent),before)
        self.assertNotIn('request_id',event);self.assertNotIn('model',event)

    def test_lost_ack_reuses_identical_payload_and_does_not_claim_success(self):
        self.club.set_sync(True);self.rows.append(self.row())
        self.club._request=Mock(side_effect=ValueError('offline'))
        with self.assertRaises(ValueError): self.club.sync_now(self.ledger)
        pending=self.club.state['pending']['envelope'];self.assertIsNone(self.club.state['last_synced_at'])
        self.club._request=self.accept;self.club.sync_now(self.ledger)
        self.assertEqual(self.sent[-1],pending);self.assertIsNotNone(self.club.state['last_synced_at'])

    def test_wrong_ack_retains_outbox(self):
        self.club.set_sync(True);self.rows.append(self.row())
        self.club._request=lambda e:{'status':'accepted','sequence':99,'hash':'wrong'}
        with self.assertRaises(ValueError): self.club.sync_now(self.ledger)
        self.assertIsNotNone(self.club.state['pending']);self.assertIsNone(self.club.state['last_synced_at'])

    def test_disconnect_failure_stops_local_sharing_and_prevents_account_switch(self):
        self.club.state['sync_enabled']=True;self.club._call=Mock(side_effect=ValueError('offline'))
        with self.assertRaises(ValueError):self.club.disconnect()
        self.assertFalse(self.club.state['sync_enabled'])
        with self.assertRaises(ValueError):self.club.start_pairing(self.ledger)

    def test_manual_unverified_link_rejected(self):
        with self.assertRaisesRegex(ValueError,'Manual secrets'):self.club.link({'handle':'fake','sync_secret':'fake'})

    def test_correction_keeps_same_event_identity(self):
        self.club.set_sync(True);self.rows.append(self.row());self.club.sync_now(self.ledger)
        first=json.loads(self.sent[-1]['payload'])['events'][0]
        self.rows[0]['input_tokens']=20;self.club.sync_now(self.ledger)
        second=json.loads(self.sent[-1]['payload'])['events'][0]
        self.assertEqual(first['event_id'],second['event_id']);self.assertEqual(second['input_tokens'],20)

    def test_pause_does_not_transmit_unsent_batch(self):
        self.club.set_sync(True);self.rows.append(self.row());self.club._request=Mock(side_effect=ValueError('offline'))
        with self.assertRaises(ValueError):self.club.sync_now(self.ledger)
        self.club._call=lambda action:{'sequence':self.club.state['sequence'],'previous_hash':self.club.state['previous_hash']}
        self.club._request=self.accept;self.club.set_sync(False)
        self.assertEqual(json.loads(self.sent[-1]['payload'])['action'],'consent');self.assertFalse(self.club.state['sync_enabled'])

    def test_connect_recovers_existing_approval_instead_of_replacing_pair(self):
        self.club.state['identity']=None
        self.club._key=Mock()
        self.club._call=Mock(return_value={'status':'connected','pairing_id':'original','handle':'alice','name':'Alice','account_id':'account','sequence':0,'previous_hash':''})
        result=self.club.start_pairing(self.ledger)
        self.assertTrue(result['is_linked']);self.assertEqual(self.club.state['pairing_id'],'original')
        self.club._call.assert_called_once_with('status')

    def test_connect_reuses_pending_session(self):
        self.club.state['identity']=None;self.club._key=Mock()
        self.club._call=Mock(return_value={'status':'pending'})
        self.club.start_pairing(self.ledger)
        self.assertEqual(self.club.state['pairing_id'],'pair')
        self.club._call.assert_called_once_with('status')

    def test_failed_start_does_not_persist_replacement_pair(self):
        self.club.state.update(identity=None,pairing_id=None);self.club._key=Mock()
        self.club._call=Mock(side_effect=ValueError('offline'))
        with self.assertRaises(ValueError):self.club.start_pairing(self.ledger)
        self.assertIsNone(self.club.state['pairing_id'])

    def test_empty_sync_explains_excluded_history(self):
        self.rows.append(self.row('old'));self.club.set_sync(True)
        result=self.club.sync_now(self.ledger)
        self.assertIn('No new usage yet',result['sync_message'])
        self.assertIsNone(result['last_synced_at'])
        self.assertEqual(len(self.sent),1)  # consent only, no fake upload

    def test_sync_reports_upload_then_up_to_date(self):
        self.club.set_sync(True);self.rows.append(self.row())
        self.assertIn('Uploaded 1 usage records',self.club.sync_now(self.ledger)['sync_message'])
        self.assertIn('Up to date',self.club.sync_now(self.ledger)['sync_message'])

    def test_models_are_optional_and_preference_preserves_pending_usage(self):
        self.club.set_sync(True)
        row=self.row();row['requested_model']='gemma4:31b';self.rows.append(row)
        self.club.sync_now(self.ledger)
        first=json.loads(self.sent[-1]['payload'])['events'][0]
        self.assertEqual(first['category'],'local')
        self.assertNotIn('model_name',first)
        self.rows.append(self.row('another'))
        self.club.set_sync(True,True)
        self.assertNotIn('another',self.club.state['baseline'])
        self.club.sync_now(self.ledger)
        event=json.loads(self.sent[-1]['payload'])['events'][0]
        self.assertEqual(event['model_name'],'gemma4:31b')
        self.assertEqual(event['event_id'],first['event_id'])
        self.club.set_sync(True,False);self.club.sync_now(self.ledger)
        self.assertTrue(all('model_name' not in e for e in json.loads(self.sent[-1]['payload'])['events']))

    def test_remote_profile_caching_and_fallback(self):
        from unittest.mock import patch, MagicMock
        fake_profile={'handle':'alice','tokens':5000,'categories':{'local':5000},'models':[],'roles':[]}
        mock_response=MagicMock()
        mock_response.status=200
        mock_response.read.return_value=json.dumps(fake_profile).encode('utf-8')
        mock_response.__enter__.return_value=mock_response

        with patch('urllib.request.urlopen',return_value=mock_response) as mock_urlopen:
            profile=self.club.get_remote_profile()
            self.assertEqual(profile['tokens'],5000)
            mock_urlopen.assert_called_once()

            mock_urlopen.reset_mock()
            profile2=self.club.get_remote_profile()
            self.assertEqual(profile2['tokens'],5000)
            mock_urlopen.assert_not_called()

            mock_urlopen.side_effect=OSError('offline')
            profile3=self.club.get_remote_profile(force=True)
            self.assertEqual(profile3['tokens'],5000)

        status=self.club.get_status(include_remote=False)
        self.assertEqual(status['remote_profile']['tokens'],5000)

    def test_remote_profile_cleared_on_disconnect(self):
        self.club._remote_profile_cache={'handle':'alice','tokens':5000}
        self.club._remote_profile_cache_time=12345
        self.club._call=Mock(return_value={'status':'disconnected'})
        self.club.disconnect()
        self.assertIsNone(self.club._remote_profile_cache)
        self.assertEqual(self.club._remote_profile_cache_time,0)

    def test_remote_profile_self_heals_when_handle_renamed(self):
        import urllib.error
        from unittest.mock import patch, MagicMock
        self.club.state['identity']={'handle':'alice','name':'Alice'}
        self.club._call=Mock(return_value={'status':'connected','handle':'cheaposnumero1','name':'Bob'})

        def fake_urlopen(req, timeout=4):
            if 'alice' in req.full_url:
                raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', hdrs={}, fp=None)
            if 'cheaposnumero1' in req.full_url:
                resp=MagicMock()
                resp.status=200
                resp.read.return_value=json.dumps({'handle':'cheaposnumero1','tokens':12345}).encode('utf-8')
                resp.__enter__.return_value=resp
                return resp
            raise ValueError('Unexpected URL')

        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            profile=self.club.get_remote_profile(force=True)
            self.assertEqual(profile['handle'],'cheaposnumero1')
            self.assertEqual(self.club.state['identity']['handle'],'cheaposnumero1')
            self.club._call.assert_called_once_with('status')
            status=self.club.get_status(include_remote=True)
            self.assertEqual(status['x_identity']['handle'],'cheaposnumero1')
            self.assertEqual(status['remote_profile']['tokens'],12345)

    def test_sync_includes_work_outcomes(self):
        self.club.set_sync(True)
        self.rows.append(self.row())
        self.ledger.summary=Mock(return_value={'completion':{'human_accepted_jobs':12,'merged_runs':60,'independent_review_approved_jobs':79}})
        self.club.sync_now(self.ledger)
        payload=json.loads(self.sent[-1]['payload'])
        self.assertIn('work_outcomes', payload)
        self.assertEqual(payload['work_outcomes']['completed_tasks'], 72)
        self.assertEqual(payload['work_outcomes']['human_accepted_jobs'], 12)
        self.assertEqual(payload['work_outcomes']['merged_runs'], 60)
        self.assertEqual(payload['work_outcomes']['review_approved_jobs'], 79)
        self.assertEqual(payload['work_outcomes']['acceptance_rate'], 91.1)

    def test_check_pairing_force_refreshes_handle(self):
        self.club.state['identity']={'handle':'alice','name':'Alice','account_id':'acc1'}
        self.club._call=Mock(return_value={'status':'connected','pairing_id':'pair','handle':'bob','name':'Bob','account_id':'acc1','sequence':1,'previous_hash':'abc'})
        self.club.check_pairing(force=False)
        self.club._call.assert_not_called()
        self.assertEqual(self.club.state['identity']['handle'],'alice')

        self.club.check_pairing(force=True)
        self.club._call.assert_called_once_with('status')
        self.assertEqual(self.club.state['identity']['handle'],'bob')

    def test_sync_includes_telemetry_respecting_share_models(self):
        self.club.set_sync(True)
        self.rows.append(self.row())
        mock_summary = {
            'completion': {'human_accepted_jobs': 5, 'merged_runs': 10, 'independent_review_approved_jobs': 15},
            'self_healing_index': {'initial_work_tokens': 10000, 'recovery_tokens': 1500, 'repair_overhead_pct': 13.0},
            'model_pairs': {
                'qwen + deepseek': {
                    'worker': 'qwen2.5-coder:32b',
                    'reviewer': 'deepseek-chat',
                    'is_independent': True,
                    'total_jobs': 8,
                    'completion_rate': 87.5,
                    'avg_tokens_per_job': 4500
                }
            },
            'models': {
                'qwen2.5-coder:32b': {
                    'requests': 10, 'successes': 9, 'failures': 1, 'total_seconds': 18.0,
                    'failure_breakdown': {'timeout': 1}
                }
            },
            'tokens': {'reasoning': 2500, 'cached': 4000}
        }
        self.ledger.summary = Mock(return_value=mock_summary)

        # When share_models is False (default)
        self.club.sync_now(self.ledger)
        payload = json.loads(self.sent[-1]['payload'])
        self.assertIn('telemetry', payload)
        telem = payload['telemetry']
        self.assertEqual(telem['self_healing']['repair_overhead_pct'], 13.0)
        self.assertEqual(telem['token_depth']['reasoning_tokens'], 2500)
        self.assertEqual(telem['token_depth']['cached_tokens'], 4000)
        self.assertEqual(telem['provider_health']['total_requests'], 10)
        self.assertEqual(telem['provider_health']['success_rate'], 90.0)
        self.assertEqual(telem['provider_health']['avg_latency_ms'], 2000)
        self.assertEqual(telem['provider_health']['failure_breakdown'], {'timeout': 1})
        # Model pairs stripped when share_models is False
        self.assertEqual(telem['model_pairs'], [])

        # When share_models is True
        self.club.set_sync(True, share_models=True)
        self.rows.append(self.row('req2'))
        self.club.sync_now(self.ledger)
        payload2 = json.loads(self.sent[-1]['payload'])
        telem2 = payload2['telemetry']
        self.assertEqual(len(telem2['model_pairs']), 1)
        self.assertEqual(telem2['model_pairs'][0]['worker'], 'qwen2.5-coder:32b')
        self.assertEqual(telem2['model_pairs'][0]['reviewer'], 'deepseek-chat')
        self.assertEqual(telem2['model_pairs'][0]['completion_rate'], 87.5)
        self.assertIn('by_provider', telem2['provider_health'])
        self.assertIn('Qwen', telem2['provider_health']['by_provider'])
        self.assertEqual(telem2['provider_health']['by_provider']['Qwen']['total_requests'], 10)

    def test_sync_event_includes_reasoning_and_cached_tokens(self):
        self.club.set_sync(True)
        r = self.row('token_depth_row')
        r['reasoning_tokens'] = 350
        r['cached_tokens'] = 800
        self.rows.append(r)
        self.club.sync_now(self.ledger)
        event = json.loads(self.sent[-1]['payload'])['events'][0]
        self.assertEqual(event['reasoning_tokens'], 350)
        self.assertEqual(event['cached_tokens'], 800)
