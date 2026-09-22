"""Small deterministic protocol checks; no network, models or keychain calls."""
import hashlib
import json
import tempfile
import unittest
from unittest.mock import Mock
from cheapos.club import ClubManager
from cheapos.club_routes import backfill_routes
import uuid

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
        self.attempts_supported=False
        def accept(envelope):
            message=json.loads(envelope['payload'])
            if message['action']=='status':
                return {'status':'connected','capabilities':['request_attempts_v1'] if self.attempts_supported else []}
            self.sent.append(envelope)
            return {'status':'accepted','sequence':message['sequence'],'hash':hashlib.sha256(envelope['payload'].encode()).hexdigest(),
                    'request_attempts_accepted':len(message.get('request_attempts', []))}
        self.accept=accept;self.club._request=accept

    def row(self,id='new',tokens=12,role='worker'):
        return {'request_id':id,'date':'2026-09-15','reconciled':True,'input_tokens':tokens,'output_tokens':3,'category':'local','club_category':'local','role':role}

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

    def test_recovered_route_uses_existing_signed_correction_and_model_consent(self):
        from cheapos.request_health import historical_route_metadata
        self.club.set_sync(True, True)
        scope = dict(base_url='http://private.invalid/v1', connection_revision='private-revision',
                     model='groq/openai/shared-model', role='worker')
        row = {**self.row(), 'requested_model': scope['model'], 'served_model': 'openai/shared-model'}
        self.rows.append(row)
        self.club.sync_now(self.ledger)
        first = json.loads(self.sent[-1]['payload'])['events'][0]
        row.update(historical_route_metadata({**row, 'dispatch_scope': scope}, [{**scope, 'gateway_type': 'omniroute'}]))
        self.club.sync_now(self.ledger)
        second = json.loads(self.sent[-1]['payload'])['events'][0]
        self.assertEqual(second['event_id'], first['event_id'])
        self.assertEqual(second['input_tokens'], first['input_tokens'])
        self.assertEqual(second['model_name'], first['model_name'])
        self.assertEqual(second['request_health']['provider'], 'groq')
        self.assertEqual(second['request_health']['gateway'], 'omniroute')
        self.assertNotIn('private.invalid', self.sent[-1]['payload'])
        self.assertNotIn('private-revision', self.sent[-1]['payload'])
        count = len(self.sent)
        self.club.sync_now(self.ledger)
        self.assertEqual(len(self.sent), count)
        self.club.set_sync(True, False)
        self.club.sync_now(self.ledger)
        private = json.loads(self.sent[-1]['payload'])['events'][0]
        self.assertNotIn('model_name', private)
        self.assertNotIn('provider', private['request_health'])
        self.assertNotIn('gateway', private['request_health'])

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
        fake_profile={'handle':'alice','tokens':5000,'categories':{'local':5000},'models':[],'roles':[],
                      'telemetry':{'padding':'x'*70000}}
        mock_response=MagicMock()
        mock_response.status=200
        raw=json.dumps(fake_profile).encode('utf-8')
        mock_response.read.side_effect=lambda size: raw[:size]
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
        self.assertIsNotNone(status['remote_profile_fetched_at'])

    def test_invalid_or_oversized_profile_never_replaces_accepted_total(self):
        from unittest.mock import patch, MagicMock
        from cheapos.club import MAX_PUBLIC_PROFILE_BYTES
        response=MagicMock(status=200)
        response.__enter__.return_value=response
        for raw in (b'{'*(MAX_PUBLIC_PROFILE_BYTES+1), b'{', b'[]', b'{"handle":"alice"}',
                    b'{"handle":"alice","tokens":false}', b'{"handle":"alice","tokens":-1}'):
            with self.subTest(sample=raw[:40]):
                response.read.side_effect=lambda size: raw[:size]
                for cached in (None, {'handle':'alice','tokens':5000}):
                    self.club._remote_profile_cache=cached
                    self.club._remote_profile_cache_time=12345 if cached else 0
                    with patch('urllib.request.urlopen',return_value=response):
                        self.assertEqual(self.club.get_remote_profile(force=True),cached)
                    response.read.assert_called_with(MAX_PUBLIC_PROFILE_BYTES+1)
                    self.assertEqual(self.club._remote_profile_cache_time,12345 if cached else 0)

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
                raw=json.dumps({'handle':'cheaposnumero1','tokens':12345,'telemetry':{'padding':'x'*70000}}).encode('utf-8')
                resp.read.side_effect=lambda size: raw[:size]
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
        self.assertNotIn('provider_health', telem)
        self.assertNotIn('model_health', telem)
        self.assertEqual(payload['events'][0]['request_health']['outcome'], 'unknown')
        self.assertNotIn('provider', payload['events'][0]['request_health'])
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
        self.assertNotIn('provider_health', telem2)
        self.assertEqual(payload2['events'][0]['request_health']['provider'], 'unknown')

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

    def test_health_only_travels_with_eligible_signed_events_and_retries_exactly(self):
        from cheapos.request_health import route_metadata
        self.rows.append(self.row('before-consent'))
        self.club.set_sync(True, True)
        for id, provider in [('a', 'antigravity'), ('b', 'openrouter')]:
            self.rows.append({**self.row(id), **route_metadata({'gateway': 'omniroute', 'model': provider+'/publisher/shared'}),
                              'served_model': 'shared', 'status': 'responded', 'seconds': 2})
        self.rows.append({**self.row('unreconciled'), 'reconciled': False})
        self.rows.append({**self.row('missing-usage'), 'input_tokens': None})
        self.club._request=Mock(side_effect=ValueError('offline'))
        with self.assertRaises(ValueError): self.club.sync_now(self.ledger)
        saved=self.club.state['pending']['envelope']
        events=json.loads(saved['payload'])['events']
        self.assertEqual(len(events),2)
        self.assertEqual([e['request_health']['provider'] for e in events],['antigravity','openrouter'])
        self.assertEqual([e['model_name'] for e in events],['shared','shared'])
        self.assertEqual(events[0]['request_health']['duration_ms'],2000)
        self.assertFalse(self.club.state['sent'])
        self.club._request=self.accept
        self.club.sync_now(self.ledger)
        self.assertEqual(saved,self.sent[-1])
        self.assertEqual(set(self.club.state['sent']),{'a','b'})

    def test_model_prefix_cannot_establish_free_access_in_signed_event(self):
        self.club.set_sync(True, True)
        self.rows.append({**self.row(), 'club_category':'unknown', 'category':'public_free',
                          'requested_model':'openrouter/vendor/model:free'})
        self.club.sync_now(self.ledger)
        self.assertEqual(json.loads(self.sent[-1]['payload'])['events'][0]['category'],'unknown')

    def prepare_route_backfill(self):
        self.rows.extend([{**self.row(rid), 'requested_model':'openrouter/vendor/model',
                           'request_gateway':'omniroute', 'request_provider':'openrouter'}
                          for rid in ('previously-shared', 'always-private')])
        self.club.set_sync(True, True)
        event_id = str(uuid.uuid5(uuid.UUID(self.club.state['installation_id']), 'previously-shared'))
        def request(envelope):
            message = json.loads(envelope['payload'])
            if message['action'] == 'route_history':
                self.sent.append(envelope)
                self.assertEqual(set(message), {'version','action','installation_id','pairing_id','event_ids'})
                return {'status':'route_history', 'event_ids':[event_id]}
            return self.accept(envelope)
        self.club._request = request
        return event_id, request

    def test_backfill_updates_only_server_confirmed_metadata_and_not_usage_eligibility(self):
        event_id, _ = self.prepare_route_backfill()
        original = json.dumps(self.rows, sort_keys=True)
        self.club.sync_now(self.ledger)
        message = json.loads(self.sent[-1]['payload'])
        self.assertEqual(message['events'], [])
        self.assertNotIn('telemetry', message)
        self.assertNotIn('work_outcomes', message)
        self.assertEqual(message['route_corrections'], [{'event_id':event_id,'gateway':'omniroute','provider':'openrouter'}])
        self.assertEqual(self.club.state['sent'], {})
        self.assertEqual(set(self.club.state['baseline']), {'previously-shared','always-private'})
        self.assertEqual(json.dumps(self.rows, sort_keys=True), original)
        self.assertIn('Token totals are unchanged', self.club.state['sync_message'])
        calls = len(self.sent)
        self.club.sync_now(self.ledger)
        self.assertEqual(len(self.sent), calls)

    def test_backfill_lost_ack_retries_same_envelope_after_restart(self):
        _, request = self.prepare_route_backfill()
        def lost_ack(envelope):
            result = request(envelope)
            if json.loads(envelope['payload'])['action'] == 'sync':
                raise ValueError('offline')
            return result
        self.club._request = lost_ack
        self.assertEqual(backfill_routes(self.club, self.ledger), 0)
        saved = self.club.state['pending']['envelope']
        self.assertNotIn('previously-shared', self.club.state['route_backfill_processed'])
        reopened = ClubManager(self.temp.name, credentials=Mock())
        reopened._request = request
        reopened._flush()
        self.assertEqual(self.sent[-1], saved)
        self.assertIn('previously-shared', reopened.state['route_backfill_processed'])
        self.assertEqual(reopened.state['sent'], {})

    def test_backfill_discovery_failure_or_unknown_route_does_not_block_normal_usage(self):
        self.prepare_route_backfill()
        def old_server(envelope):
            if json.loads(envelope['payload'])['action'] == 'route_history':
                raise ValueError('unsupported')
            return self.accept(envelope)
        self.club._request = old_server
        self.rows.append(self.row('new'))
        self.club.sync_now(self.ledger)
        self.assertIn('new', self.club.state['sent'])
        self.assertIsNone(self.club.state['pending'])
        self.assertIsNone(self.club.state['error'])
        self.assertEqual(self.club.state['route_backfill_error'], 'unsupported')
        for row in self.rows: row.pop('request_provider', None)
        self.club._route_backfill_retry_at = 0
        self.club._request = Mock(side_effect=AssertionError('No metadata may be inferred from a model prefix'))
        self.assertEqual(backfill_routes(self.club, self.ledger), 0)

    def test_backfill_honors_model_consent_and_rejects_unrequested_ids(self):
        self.prepare_route_backfill()
        self.club._request = Mock(side_effect=AssertionError('Sharing is off'))
        self.club.state['share_models'] = False
        self.assertEqual(backfill_routes(self.club, self.ledger), 0)
        self.club.state['share_models'] = True
        self.club._request = Mock(return_value={'status':'route_history','event_ids':[str(uuid.uuid4())]})
        self.assertEqual(backfill_routes(self.club, self.ledger), 0)
        self.assertIsNone(self.club.state['pending'])
        self.assertEqual(self.club.state['route_backfill_processed'], {})

    def test_backfill_batches_continue_and_model_consent_rechecks_saved_metadata(self):
        self.rows.extend([{**self.row(str(n)), 'request_gateway':'omniroute', 'request_provider':'openrouter'} for n in range(101)])
        self.club.set_sync(True, True)
        def request(envelope):
            message = json.loads(envelope['payload'])
            if message['action'] == 'route_history':
                return {'status':'route_history','event_ids':message['event_ids']}
            return self.accept(envelope)
        self.club._request = request
        self.assertEqual(backfill_routes(self.club, self.ledger), 100)
        self.assertEqual(backfill_routes(self.club, self.ledger), 1)
        self.assertEqual(backfill_routes(self.club, self.ledger), 0)
        self.assertEqual(len(self.club.state['route_backfill_processed']), 101)
        self.assertEqual(self.club.state['sent'], {})
        self.club.set_sync(True, False)
        self.assertEqual(backfill_routes(self.club, self.ledger), 0)
        self.club.set_sync(True, True)
        self.assertEqual(backfill_routes(self.club, self.ledger), 100)

    def test_pause_reconciles_backfill_ack_without_promoting_usage(self):
        _, request = self.prepare_route_backfill()
        def lost_ack(envelope):
            result = request(envelope)
            if json.loads(envelope['payload'])['action'] == 'sync':
                raise ValueError('offline')
            return result
        self.club._request = lost_ack
        backfill_routes(self.club, self.ledger)
        envelope = self.club.state['pending']['envelope']
        message = json.loads(envelope['payload'])
        self.club._call = Mock(return_value={'sequence':message['sequence'],'previous_hash':hashlib.sha256(envelope['payload'].encode()).hexdigest()})
        self.club._request = request
        self.club.set_sync(False)
        self.assertFalse(self.club.state['sync_enabled'])
        self.assertEqual(self.club.state['sent'], {})
        self.assertIn('previously-shared', self.club.state['route_backfill_processed'])
        self.assertEqual(json.loads(self.sent[-1]['payload'])['action'], 'consent')

    def attempt_row(self, rid='failed', status='failed'):
        return {**self.row(rid), 'status':status, 'reconciled':False, 'input_tokens':None, 'output_tokens':None,
                'requested_model':'test/model', 'request_gateway':'omniroute', 'request_provider':'test',
                'seconds':0.5, 'failure_category':'rate_limit_quota', 'prompt':'private text', 'error':'private error'}

    def test_attempts_without_tokens_are_signed_separately_and_later_usage_keeps_identity(self):
        self.attempts_supported=True
        self.club.set_sync(True, True)
        row=self.attempt_row();self.rows.append(row)
        self.club.sync_now(self.ledger)
        payload=json.loads(self.sent[-1]['payload'])
        self.assertEqual(payload['events'], [])
        attempt=payload['request_attempts'][0]
        self.assertEqual(attempt['request_health']['failure_category'], 'rate_limit_quota')
        self.assertEqual(attempt['request_health']['duration_ms'], 500)
        self.assertNotIn('private', self.sent[-1]['payload'])
        self.assertFalse({'input_tokens','output_tokens','accounted_tokens','task_id'} & set(attempt))
        self.assertEqual(self.club.state['sent'], {})
        self.assertIn('failed', self.club.state['attempts_sent'])
        before=len(self.sent);self.club.sync_now(self.ledger);self.assertEqual(len(self.sent), before)
        row.update(reconciled=True,input_tokens=9,output_tokens=2)
        self.club.sync_now(self.ledger)
        later=json.loads(self.sent[-1]['payload'])
        self.assertEqual(later['events'][0]['event_id'], attempt['event_id'])
        self.assertNotIn('request_attempts', later)
        self.assertEqual(later['events'][0]['input_tokens'], 9)

    def test_attempts_honor_consent_terminal_status_and_older_servers(self):
        self.rows.append(self.attempt_row('private-before-consent'))
        self.club.set_sync(True)
        self.rows.extend([self.attempt_row(), self.attempt_row('pending','pending'), self.attempt_row('cancelled','cancelled')])
        before=len(self.sent);self.club.sync_now(self.ledger);self.assertEqual(len(self.sent), before)
        self.attempts_supported=True
        self.club.sync_now(self.ledger)
        attempts=json.loads(self.sent[-1]['payload'])['request_attempts']
        self.assertEqual(len(attempts), 2)
        self.assertEqual({a['request_health']['outcome'] for a in attempts}, {'failed','cancelled'})
        self.assertTrue(all('model_name' not in a and 'provider' not in a['request_health'] for a in attempts))
        self.assertNotIn('private-before-consent', self.club.state['attempts_sent'])
        self.club.set_sync(False)
        self.rows.append(self.attempt_row('private-while-paused'))
        self.club.set_sync(True)
        self.assertIn('private-while-paused', self.club.state['baseline'])
        self.assertNotIn('failed', self.club.state['baseline'])

    def test_attempt_outbox_replays_exactly_and_requires_explicit_acknowledgment(self):
        self.attempts_supported=True;self.club.set_sync(True)
        self.rows.append(self.attempt_row())
        def missing_ack(envelope):
            response=self.accept(envelope)
            response.pop('request_attempts_accepted', None)
            return response
        self.club._request=missing_ack
        with self.assertRaisesRegex(ValueError, 'did not acknowledge'): self.club.sync_now(self.ledger)
        saved=self.club.state['pending']['envelope']
        self.assertFalse(self.club.state.get('attempts_sent'))
        self.club._request=self.accept;self.club.sync_now(self.ledger)
        self.assertEqual(self.sent[-1], saved)
        self.assertIn('failed', self.club.state['attempts_sent'])

    def test_attempt_corrections_privacy_and_bounded_batches(self):
        self.attempts_supported=True;self.club.set_sync(True, True)
        self.rows.extend(self.attempt_row(str(i)) for i in range(41))
        self.club.sync_now(self.ledger)
        first=json.loads(self.sent[-1]['payload'])['request_attempts']
        self.assertEqual(len(first), 40)
        self.club.sync_now(self.ledger)
        self.assertEqual(len(json.loads(self.sent[-1]['payload'])['request_attempts']), 1)
        self.rows[0].update(status='responded',seconds=1)
        self.club.sync_now(self.ledger)
        correction=json.loads(self.sent[-1]['payload'])['request_attempts'][0]
        self.assertEqual(correction['event_id'], first[0]['event_id'])
        self.assertEqual(correction['request_health']['outcome'], 'responded')
        self.assertNotIn('failure_category', correction['request_health'])
        self.club.set_sync(True, False);self.club.sync_now(self.ledger)
        self.assertTrue(all('model_name' not in a and 'provider' not in a['request_health']
                            for a in json.loads(self.sent[-1]['payload'])['request_attempts']))

    def test_lifetime_journal_only_exports_dispatched_non_synthetic_attempts(self):
        from cheapos.lifetime_usage import LifetimeUsage
        journal=LifetimeUsage(self.temp.name)
        self.attempts_supported=True;self.club.set_sync(True)
        record=dict(id='real',dispatched=True,requested_at='2026-09-20T12:00:00Z',status='failed',
                    failure_category='rate_limit_quota',reservation={'tokens':1000},usage_reconciled=False)
        journal.ingest(dict(id='fixture',request_metrics=[record,{**record,'id':'not-dispatched','dispatched':False},
                                                              {**record,'id':'synthetic','synthetic':True}]))
        self.club.sync_now(journal)
        payload=json.loads(self.sent[-1]['payload'])
        self.assertEqual(payload['events'], [])
        self.assertEqual(len(payload['request_attempts']), 1)
        self.assertNotIn('duration_ms', payload['request_attempts'][0]['request_health'])

    def test_usage_and_attempts_share_envelope_capacity_without_starvation(self):
        self.attempts_supported=True;self.club.set_sync(True, True)
        self.rows.extend({**self.attempt_row(str(i)), 'reconciled':True, 'input_tokens':1000000000,
                          'output_tokens':1000000000, 'requested_model':'m'*160, 'request_provider':'p'*64,
                          'request_gateway':'g'*64, 'failure_category':'f'*64} for i in range(41))
        self.club.sync_now(self.ledger)
        envelope=self.sent[-1];payload=json.loads(envelope['payload'])
        self.assertEqual(len(payload['events']),20)
        self.assertEqual(len(payload['request_attempts']),20)
        self.assertLess(len(envelope['payload']),50000)
        self.assertLess(len(json.dumps(envelope)),60000)
        self.assertEqual(len(self.club.state['sent']),20)
        self.assertEqual(len(self.club.state['attempts_sent']),20)
        self.club.sync_now(self.ledger);self.club.sync_now(self.ledger)
        self.assertEqual(len(self.club.state['sent']),41)
        self.assertEqual(len(self.club.state['attempts_sent']),41)

    def test_pause_reconciles_attempt_ack_and_later_usage_remains_eligible(self):
        self.attempts_supported=True;self.club.set_sync(True)
        self.rows.append(self.attempt_row())
        def lost_ack(envelope):
            response=self.accept(envelope)
            if json.loads(envelope['payload'])['action']=='sync': raise ValueError('offline')
            return response
        self.club._request=lost_ack
        with self.assertRaises(ValueError): self.club.sync_now(self.ledger)
        envelope=self.club.state['pending']['envelope'];message=json.loads(envelope['payload'])
        self.club._call=Mock(return_value={'sequence':message['sequence'],'previous_hash':hashlib.sha256(envelope['payload'].encode()).hexdigest()})
        self.club._request=self.accept;self.club.set_sync(False)
        self.assertIn('failed',self.club.state['attempts_sent'])
        self.club.set_sync(True)
        self.assertNotIn('failed',self.club.state['baseline'])
        self.rows[0].update(reconciled=True,input_tokens=10,output_tokens=1)
        self.club.sync_now(self.ledger)
        self.assertEqual(json.loads(self.sent[-1]['payload'])['events'][0]['input_tokens'],10)
