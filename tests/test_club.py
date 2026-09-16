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

    def row(self,id='new',tokens=12):
        return {'request_id':id,'date':'2026-09-15','reconciled':True,'input_tokens':tokens,'output_tokens':3,'category':'local','club_category':'unknown'}

    def test_opt_in_excludes_existing_usage_and_duplicate_ticks(self):
        self.rows.append(self.row('old'));self.club.set_sync(True)
        self.rows.append(self.row());self.club.sync_now(self.ledger)
        event=json.loads(self.sent[-1]['payload'])['events'][0]
        self.assertEqual(event['input_tokens'],12)
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
