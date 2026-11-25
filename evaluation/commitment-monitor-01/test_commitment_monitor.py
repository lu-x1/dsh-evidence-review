import unittest
from commitment_monitor import MonitorState,split_reply


class StateTests(unittest.TestCase):
    def setUp(self):
        self.s=MonitorState('toy');self.refs=[{'id':'u1','text':'Keep the old interface format.'}]
        self.s.ingest('toy',self.refs)
        self.issue={'candidate_quote':'changed format','requirement_quotes':['Keep the old interface format.'],
            'diagnosis':'The old interface changed.','reminder':'Check the old interface.'}

    def review(self):
        return {'assessment':'drift','audit':[{'dimension':'scope','requirement':'Old interface unchanged',
            'requirement_quotes':['Keep the old interface format.'],'updates':[], 'status':'conflict'}], 'issues':[self.issue]}

    def test_same_model_agreement_does_not_make_authority(self):
        self.s.observe('r1',self.review(),[],[])
        self.assertEqual(self.s.view()['automatically_confirmed_contracts'],0)
        self.assertEqual(self.s.interpretations[0]['semantic_status'],'provisional_not_authority')

    def test_new_user_change_is_visible_without_erasing_old_source(self):
        self.s.observe('r1',self.review(),[],[])
        self.s.ingest('toy',self.refs+[{'id':'u2','text':'For the new export only, use a new format.'}])
        self.assertEqual(self.s.view()['new_user_message_refs'][0]['source_id'],'u2')
        self.assertEqual(len(self.s.sources),2);self.assertEqual(len(self.s.findings),1)

    def test_actor_promise_cannot_close_issue(self):
        self.s.observe('r1',self.review(),[],[]);ident=next(iter(self.s.findings))
        self.s.observe('r2',{'audit':[],'issues':[]},[{'issue_id':ident,'status':'repair_observed',
            'requirement_quotes':['Keep the old interface format.'],'evidence_quotes':['I fixed it.']}],[])
        self.assertEqual(self.s.findings[ident]['resolution_proposals'],[])
        self.assertEqual(self.s.findings[ident]['state'],'open_unverified_finding')

    def test_grounded_resolution_is_still_only_a_proposal(self):
        self.s.observe('r1',self.review(),[],[]);ident=next(iter(self.s.findings))
        self.s.observe('r2',{'audit':[],'issues':[]},[{'issue_id':ident,'status':'repair_observed',
            'requirement_quotes':['Keep the old interface format.'],'evidence_quotes':['old format test passed']}],['old format test passed'])
        self.assertEqual(len(self.s.findings[ident]['resolution_proposals']),1)
        self.assertEqual(self.s.findings[ident]['state'],'open_unverified_finding')

    def test_rewrite_or_cross_task_source_is_rejected(self):
        with self.assertRaises(ValueError):self.s.ingest('another',self.refs)
        with self.assertRaises(ValueError):self.s.ingest('toy',[{'id':'u1','text':'Different text'}])

    def test_bad_source_batch_has_no_partial_effect(self):
        before=self.s.snapshot()
        with self.assertRaises(ValueError):
            self.s.ingest('toy',self.refs+[{'id':'u2','text':'Valid'}, {'id':'u3','text':None}])
        self.assertEqual(self.s.snapshot(),before)

    def test_unknown_quote_not_promoted_and_duplicate_review_rejected(self):
        r=self.review();r['audit'][0]['requirement_quotes']=['Actor invented this.'];r['issues']=[]
        self.assertIn('interpretation_source_not_resolved',self.s.observe('r1',r,[],[]))
        self.assertEqual(self.s.interpretations,[])
        with self.assertRaises(ValueError):self.s.observe('r1',r,[],[])

    def test_bad_sidecar_does_not_discard_review(self):
        review=self.review();actual,follow,warnings=split_reply({'review':review,'follow_up':'bad'})
        self.assertEqual(actual,review);self.assertEqual(follow,[]);self.assertTrue(warnings)


if __name__=='__main__':unittest.main()
