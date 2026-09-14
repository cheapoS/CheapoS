import tempfile
import unittest
from unittest.mock import patch, Mock
from threading import RLock
from cheapos.branch_controller import BranchController
from cheapos import unattended_setup as setup


class SetupTests(unittest.TestCase):
    def test_preflight_blocks_missing_prerequisite_without_running_commands(self):
        with tempfile.TemporaryDirectory() as root:
            task={'workspace':root,'planning_assumptions':['Follow existing toolbar style.']}
            scope=[{'command':['python3','-m','pytest'],'profile':None}]
            with patch.object(setup.environment,'inspect',return_value={'status':'missing','evidence':'pytest absent.','next_step':'Prepare declared environment.'}) as inspect:
                result=setup.inspect(task,scope)
                self.assertFalse(result['ready']);self.assertEqual(inspect.call_count,1)
                self.assertIn('pytest absent',result['checks'][1]['detail'])
                with self.assertRaisesRegex(ValueError,'before Start'):setup.require_ready(task,scope)
            with patch.object(setup.environment,'inspect',return_value={'status':'ready'}):
                result=setup.require_ready(task,scope)
                self.assertEqual(result['assumptions'],task['planning_assumptions'])
                self.assertIn('exactly',result['checks'][1]['detail'])

    def test_unavailable_directory_cannot_be_ready(self):
        with patch.object(setup.environment,'inspect',return_value={'status':'ready'}):
            self.assertFalse(setup.inspect({'workspace':'/nonexistent/cheapos-test-directory'},[{'command':['python3']}])['ready'])

    def test_context_recheck_is_once_per_item_and_preserves_real_questions(self):
        item={'id':'one'}
        task={'branch_run':{'plan':{'continue_independent':True},'authorization_ref':'approved','current_item_id':'one','items':[item]}}
        self.assertTrue(setup.reconsider_question(task,'What stack?'))
        self.assertFalse(setup.reconsider_question(task,'Need an essential decision.'))
        self.assertEqual(item['clarification_candidate'],'What stack?')
        self.assertFalse(setup.reconsider_question({},'Interactive question'))
        task['branch_run'].pop('authorization_ref')
        item.pop('clarification_rechecked')
        self.assertFalse(setup.reconsider_question(task,'Unapproved question'))

    def test_active_guidance_preserves_deferred_questions(self):
        blocked={'id':'one','question':'Which behavior?'}
        run={'status':'running','current_item_id':'two','items':[blocked]}
        task={'status':'running','branch_run':run}
        engine=Mock(lock=RLock(),runtimes={})
        engine.store.get.return_value=task
        controller=object.__new__(BranchController)
        controller.engine=engine
        controller.validate_authority=Mock()
        with patch('cheapos.branch_controller.state.require_supported',return_value=run):
            controller.message('task',{'message':'Keep working on item two.'})
            self.assertEqual(blocked['question'],'Which behavior?')
            run['waiting_for_user']='Which behavior?'
            run['status']='paused';task['status']='paused'
            controller.message('task',{'message':'Use the existing behavior.'})
        self.assertNotIn('question',blocked)
        self.assertEqual(blocked['clarification_history'][0]['question'],'Which behavior?')
