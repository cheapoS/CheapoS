"""Recurrence authority and restart safety, using a fake clock and no providers."""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos.branch_runs import new_run
from cheapos.schedules import Schedules


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.now = 1000
        self.root = Path(temp.name)
        self.project = {'source': '/fixture', 'source_identity': ['fixture', 1, 2], 'common_identity': ['git', 1, 3]}
        check = 'python3 -m unittest test_one'
        plan = {'items': [{'id': 'one', 'title': 'Watch announcements', 'instructions': 'Inspect official sources',
                 'acceptance_criteria': ['Only verified announcements'], 'required_checks': [check]}],
                'limits': {'dollars': 0}, 'final_checks': [check]}
        run = new_run(plan, target_ref='refs/heads/main')
        run.update(status='merged', authorization_ref='approved')
        self.task = {'id': 'original', 'source': '/fixture', 'prompt': 'Read https://provider.example/news',
                     'branch_run': run, 'settings_snapshot': {'values': {'roles': {'worker': {'model': 'pinned'}}}}}
        self.tasks = {'original': self.task}
        self.engine = SimpleNamespace(lock=threading.RLock(), store=SimpleNamespace(root=self.root, tasks=self.tasks,
            get=lambda key: copy.deepcopy(self.tasks[key]), save=lambda t: self.tasks.update({t['id']: copy.deepcopy(t)})),
            settings_policy=Mock(), branch=Mock(), event=Mock(), admission=Mock())
        self.engine.admission.snapshot.return_value = {'unattended': {'allowed': True}}
        self.engine.admission.pending = {}
        self.engine.branch.prepare.side_effect = self.prepare
        identity = patch('cheapos.schedules.inspect_source', return_value=self.project)
        identity.start(); self.addCleanup(identity.stop)
        self.schedules = Schedules(self.engine, lambda: self.now)

    def prepare(self, values, *, captured_settings, reserved_task_id):
        self.assertEqual(values['command_backend'], self.task.get('command_backend', 'host'))
        # A fresh receipt must be requested even though the template was approved.
        self.assertEqual(self.engine.admission.pending[reserved_task_id], 'unattended')
        task = {'id': reserved_task_id, 'branch_run': {'status': 'awaiting_authorization'}}
        self.tasks[reserved_task_id] = task
        return {'task_id': reserved_task_id, 'proposal_id': 'fresh-proposal'}

    def create(self, **changes):
        values = {'task_id': 'original', 'name': 'Watch sources', 'interval_hours': 6,
                  'approval_digest': self.schedules.preview('original')['approval_digest'],
                  'approved': True, 'allow_task_commands': True, **changes}
        result = self.schedules.create(values)['schedules'][0]['id']
        self.task = self.tasks['original']
        return result

    def unstarted(self):
        self.task['branch_run'].update(status='awaiting_authorization', authorization_ref=None)
        self.task['planning_request'] = {'schedule_request': {'interval_hours': 12}}
        preview = self.schedules.proposal(self.task)['schedule_preview']
        return {'proposal_id': 'first', 'approved': True, 'allow_task_commands': True,
                'schedule': {**preview, 'approved': True}}

    def test_frequency_is_only_intent_and_current_proposal_binds_recurrence(self):
        values = self.unstarted()
        self.assertFalse(self.schedules.records)
        with self.assertRaises(ValueError): self.schedules.preview('original')
        for change in ({'approved': False}, {'interval_hours': True}, {'approval_digest': 'stale'}, {'unknown': 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.schedules.validate_start(self.task, {**values, 'schedule': {**values['schedule'], **change}})
        with self.assertRaises(ValueError): self.schedules.validate_start(self.task, {**values, 'allow_task_commands': False})
        pending = self.schedules.validate_start(self.task, values)
        self.assertEqual(pending['interval_hours'], 12)
        self.assertFalse(self.schedules.records)
        self.task['branch_run']['plan']['items'][0]['instructions'] = 'Changed scope'
        with self.assertRaisesRegex(ValueError, 'changed'): self.schedules.validate_start(self.task, values)

    def test_recurring_full_suite_permission_is_separate(self):
        self.task['branch_run']['plan']['final_checks'] = ['python3 -m unittest discover']
        values = self.unstarted()
        with self.assertRaisesRegex(ValueError, 'full-suite'):
            self.schedules.validate_start(self.task, {**values, 'full_suite_approved': True})
        values['schedule']['full_suite_approved'] = True
        self.assertTrue(self.schedules.validate_start(self.task, values)['full_suite_approved'])

    def test_saved_combined_approval_recovers_failed_schedule_write_before_dispatch(self):
        values = self.unstarted()
        self.task['schedule_start'] = self.schedules.validate_start(self.task, values)
        self.task['branch_run']['authorization_ref'] = 'approved'
        self.engine.store.save(self.task)
        with patch.object(self.schedules, 'save', side_effect=OSError('disk busy')):
            with self.assertRaises(OSError): self.schedules.complete_start(self.task)
        self.assertFalse(self.schedules.records)
        self.assertIn('schedule_start', self.tasks['original'])
        restored = Schedules(self.engine, lambda: self.now)
        task = self.engine.store.get('original')
        restored.complete_start(task)
        self.assertEqual(len(restored.records), 1)
        self.assertEqual(task['schedule']['interval_hours'], 12)
        self.assertNotIn('schedule_start', self.tasks['original'])
        restored.complete_start(task)
        self.assertEqual(len(restored.records), 1)
        self.assertEqual(restored.validate_start(task, values)['proposal_id'], 'first')
        with self.assertRaisesRegex(ValueError, 'different'):
            restored.validate_start(task, {**values, 'schedule': {**values['schedule'], 'interval_hours': 24}})

    def test_lost_task_receipt_after_schedule_save_replays_without_duplicate(self):
        values = self.unstarted()
        self.task['schedule_start'] = self.schedules.validate_start(self.task, values)
        self.task['branch_run']['authorization_ref'] = 'approved'
        self.engine.store.save(self.task)
        with patch.object(self.engine.store, 'save', side_effect=OSError('task write failed')):
            with self.assertRaises(OSError): self.schedules.complete_start(self.task)
        self.assertEqual(len(self.schedules.records), 1)
        restored = Schedules(self.engine, lambda: self.now)
        restored.complete_start(self.engine.store.get('original'))
        self.assertEqual(len(restored.records), 1)
        self.assertNotIn('schedule_start', self.tasks['original'])
        self.now += 86400
        restored.tick()
        self.engine.branch.prepare.assert_not_called()

    def test_saved_status_tracks_disable_and_removal_without_losing_chat(self):
        key = self.create()
        self.assertEqual(self.tasks['original']['schedule']['interval_hours'], 6)
        self.schedules.update(key, {'enabled': False})
        self.assertFalse(self.tasks['original']['schedule']['enabled'])
        self.schedules.remove(key)
        self.assertNotIn('schedule', self.tasks['original'])
        self.assertEqual(self.tasks['original']['branch_run']['status'], 'merged')

    def test_due_run_retains_settings_and_gets_fresh_authority_without_overlap(self):
        self.task['command_backend'] = 'bubblewrap'
        key = self.create()
        self.schedules.tick(); self.engine.branch.prepare.assert_not_called()
        self.task['settings_snapshot']['values']['roles']['worker']['model'] = 'later-default'
        self.now += 6 * 3600
        self.schedules.tick()
        call = self.engine.branch.prepare.call_args
        self.assertEqual(call.kwargs['captured_settings']['values']['roles']['worker']['model'], 'pinned')
        self.assertEqual(call.args[0]['base_ref'], 'refs/heads/main')
        self.assertEqual(call.args[0]['plan']['limits'], {'dollars': 0})
        task_id = call.kwargs['reserved_task_id']
        self.assertEqual(json.loads(self.schedules.path.read_text())['schedules'][key]['last_task_id'], task_id)
        self.engine.branch.authorize.assert_called_once_with(task_id, {'proposal_id': 'fresh-proposal', 'approved': True,
            'allow_task_commands': True, 'full_suite_approved': False}, background=True)
        self.assertFalse(self.engine.admission.pending)
        self.now += 1000000
        for status in ('running', 'paused', 'ready_for_merge', 'left_on_branch'):
            self.tasks[task_id]['branch_run']['status'] = status
            self.schedules.tick()
        self.engine.branch.prepare.assert_called_once()
        self.assertIn('Waiting', self.schedules.view()['schedules'][0]['waiting'])
        self.tasks[task_id]['branch_run']['status'] = 'merged'
        self.schedules.tick()
        self.assertEqual(self.engine.branch.prepare.call_count, 2)

    def test_restart_coalesces_missed_ticks_and_keeps_uncertain_claim(self):
        key = self.create()
        self.now += 10 * 86400
        self.engine.branch.prepare.side_effect = RuntimeError('crash before task save')
        self.schedules.tick()
        restored = Schedules(self.engine, lambda: self.now)
        for _ in range(4): restored.tick()
        self.engine.branch.prepare.assert_called_once()
        self.assertEqual(len(restored.records[key]['history']), 1)
        self.assertIn('missing', restored.view()['schedules'][0]['waiting'])

    def test_busy_slot_and_disable_do_not_dispatch_or_consume_occurrences(self):
        key = self.create(); self.now += 86400
        self.engine.admission.snapshot.return_value['unattended']['allowed'] = False
        self.schedules.tick()
        self.assertEqual(self.schedules.records[key]['history'], [])
        self.schedules.update(key, {'enabled': False})
        self.engine.admission.snapshot.return_value['unattended']['allowed'] = True
        self.schedules.tick(); self.engine.branch.prepare.assert_not_called()
        with self.assertRaises(ValueError): self.schedules.run_now(key)
        self.schedules.remove(key)
        self.assertIn('original', self.tasks)

    def test_disable_during_preparation_keeps_new_task_but_does_not_start_it(self):
        key = self.create(); self.now += 86400
        def prepare(*args, **kwargs):
            result = self.prepare(*args, **kwargs)
            self.schedules.update(key, {'enabled': False})
            return result
        self.engine.branch.prepare.side_effect = prepare
        self.schedules.tick()
        self.engine.branch.authorize.assert_not_called()
        self.assertIn(self.schedules.records[key]['last_task_id'], self.tasks)

    def test_no_change_review_must_still_validate_current_candidate(self):
        key = self.create(); self.now += 86400
        self.task['branch_run'].update(status='ready_for_merge', items=[{'status': 'satisfied_without_change'}],
                                      readiness={'manifest': {'diff': ''}})
        with patch('cheapos.branch_final.validate', side_effect=ValueError('stale')) as validate:
            self.schedules.tick()
            validate.assert_called_once()
        self.engine.branch.prepare.assert_not_called()
        self.assertIn('no-change', self.schedules.records[key]['error'])

    def test_consent_stale_preview_unknown_fields_and_paid_plan_rejected(self):
        for changes in ({'approved': False}, {'allow_task_commands': False}, {'interval_hours': True},
                        {'approval_digest': 'old'}, {'model': 'injected'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.create(**changes)
        self.assertFalse(self.schedules.records)
        self.task['branch_run']['plan']['limits']['dollars'] = 1
        with self.assertRaisesRegex(ValueError, '\\$0'): self.schedules.preview('original')

    def test_full_suite_approval_is_not_silently_inherited(self):
        self.task['branch_run']['plan']['final_checks'] = ['python3 -m unittest discover']
        with self.assertRaisesRegex(ValueError, 'full-suite'): self.create()
        self.create(full_suite_approved=True)

    def test_corrupt_storage_fails_closed_and_is_not_overwritten(self):
        self.schedules.path.write_text('{broken')
        restored = Schedules(self.engine, lambda: self.now)
        restored.tick()
        self.assertTrue(restored.view()['error'])
        with self.assertRaises(ValueError): restored.save()
        self.assertEqual(self.schedules.path.read_text(), '{broken')

    def test_replaced_project_and_duplicate_schedule_cannot_start(self):
        self.create()
        with self.assertRaisesRegex(ValueError, 'already has'): self.create()
        self.now += 86400
        with patch('cheapos.schedules.inspect_source', return_value={'source': 'replaced'}): self.schedules.tick()
        self.engine.branch.prepare.assert_not_called()


if __name__ == '__main__': unittest.main()
