"""Tiny dispute ledger cases; no engines, repositories, or inference."""
import copy,json,unittest
from cheapos import review_disputes as disputes
from test_branch_disagreement import defect

class DisputeTests(unittest.TestCase):
    def test_shifted_paraphrase_preserves_counterevidence_and_stops(self):
        task={'branch_run':{}};item={'id':'one'}
        repair={'candidate_id':'c1','defects':[defect()]};disputes.register(task,item,repair)
        item['review_repair']=repair;key=repair['finding_ids'][0]
        args={'repair_dispositions':[{'finding_id':key,'candidate_id':'c1','disposition':'disproved','evidence':'tests/test_decimal.py:5 and passing check 7'}]}
        disputes.dispositions(task,item,args,'c2')
        task=json.loads(json.dumps(task))
        for c in ('c2','c3'):
            revised={'candidate_id':c,'defects':[dict(defect(),finding_id=key,location='report.py:30',observed='Same claim reworded')]}
            disputes.register(task,item,revised)
            self.assertEqual(revised['prior_counterevidence'][0]['disposition'],'disproved')
        from cheapos.branch_pause import PauseError
        with self.assertRaises(PauseError):disputes.register(task,item,revised)
        self.assertNotEqual(task['branch_run']['dispute_ledger']['findings'][key]['status'],'independently_resolved')

    def test_distinct_claims_are_only_possible_matches_and_resolution_is_independent(self):
        task={'branch_run':{}};item={'id':'one'}
        first={'candidate_id':'c','defects':[defect()]};disputes.register(task,item,first)
        second={'candidate_id':'c','defects':[dict(defect(),expected='Reject NaN',observed='Accepts NaN')]};disputes.register(task,item,second)
        self.assertNotEqual(first['finding_ids'],second['finding_ids'])
        records=task['branch_run']['dispute_ledger']['findings'];self.assertEqual(len(records),2)
        item['review_repair']=first;disputes.resolved(task,item,'fixed')
        regression=copy.deepcopy(first);regression['candidate_id']='regression';disputes.register(task,item,regression)
        self.assertNotEqual(first['finding_ids'],regression['finding_ids'])

    def test_focused_dispositions_preserve_unaffected_patch_and_need_evidence(self):
        finding=defect();task={'branch_run':{}};item={'id':'one'}
        a='diff --git a/report.py b/report.py\n-old\n+new\n'
        b='diff --git a/helper.py b/helper.py\n+unchanged helper\n'
        repair={'candidate_id':'old','defects':[finding],'source_patch':a+b}
        disputes.register(task,item,repair);item['review_repair']=repair
        task['patch']=a.replace('+new','+corrected')+b
        args={'repair_dispositions':[{'finding_id':repair['finding_ids'][0],'candidate_id':'old','disposition':'reproduced_and_corrected','evidence':'report.py:12 and check record 3'}]}
        disputes.dispositions(task,item,args,'new')
        self.assertEqual(disputes.brief(repair)['dispositions'][0]['reviewed_candidate_id'],'new')
        task['patch']+='diff --git a/unrelated.py b/unrelated.py\n+new unrelated behavior\n'
        with self.assertRaisesRegex(ValueError,'broader_edit_reason'):disputes.dispositions(task,item,args,'newer')
        args['repair_dispositions'][0]['evidence']=''
        with self.assertRaises(ValueError):disputes.dispositions(task,item,args,'newer')

    def test_revision_reuses_original_requirement_finding_identity(self):
        task={'branch_run':{}};item={'id':'first','acceptance_criteria':['exact values']}
        repair={'candidate_id':'old','defects':[defect()]};disputes.register(task,item,repair)
        key=repair['finding_ids'][0]
        revision={'id':'revision-1','acceptance_criteria':['exact values']}
        later={'candidate_id':'new','requirement_refs':[{'id':'first:1','item_id':'first','criterion':'exact values'}], 'defects':[dict(defect(),finding_id=key)]}
        disputes.register(task,revision,later)
        self.assertEqual(later['finding_ids'],[key])

    def test_pending_findings_cannot_authorize_their_own_criterion(self):
        from cheapos import branch_disagreement as disagreement
        item={'id':'one','acceptance_criteria':['exact values'],'review_repair':{'defects':[dict(defect(),criterion='unrelated')]}}
        task={'branch_run':{'current_item_id':'one','items':[item],'plan':{'items':[{'id':'one','acceptance_criteria':['exact values']}]}},'checks':[]}
        with self.assertRaises(ValueError):disagreement.before_write(task,'report.py')

    def test_optional_advice_does_not_become_a_blocking_finding(self):
        from cheapos import branch_disagreement as disagreement
        result={'decision':'APPROVE','suggestions':['Optional: rename a helper.']}
        self.assertEqual(disagreement.decision(result),'APPROVE')
        with self.assertRaises(ValueError):disagreement.validate({'decision':'REQUEST_CHANGES','suggestions':result['suggestions']},['exact values'])
