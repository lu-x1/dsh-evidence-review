import json
import unittest
import compact_view as C


class CompactContextTests(unittest.TestCase):
    def body(self):
        payload={'candidate':'same candidate','original_user_messages':['all user words'],
            'execution_code_index':{'provenance':'archived original prefix','entries':[{'code':'a=b+c','line':3}]}}
        return {'model':'same-model','reasoning_effort':'high','max_tokens':16384,'tools':[{'name':'same'}],
            'messages':[{'role':'system','content':'same system'},
                {'role':'assistant','content':'earlier interpretation','reasoning_content':'OPAQUE_PRIVATE_TEST_MARKER'},
                {'role':'tool','content':'old observation'},
                {'role':'user','content':'same reviewer instructions\n\n'+json.dumps(payload)}]}

    def test_only_system_and_review_view_remain_with_original_evidence_and_resources(self):
        body=self.body();out=C.compose(body)
        self.assertEqual([v['role'] for v in out['messages']],['system','user'])
        self.assertEqual(out['messages'][0],body['messages'][0])
        self.assertEqual({k:v for k,v in out.items() if k!='messages'},{k:v for k,v in body.items() if k!='messages'})
        data=json.loads(out['messages'][-1]['content'].split('\n\n',1)[1])
        self.assertEqual(data['candidate'],'same candidate');self.assertEqual(data['original_user_messages'],['all user words'])
        self.assertEqual(data['execution_code_index']['entries'],[{'code':'a=b+c','line':3}])
        self.assertNotIn('OPAQUE_PRIVATE_TEST_MARKER',json.dumps(out))
        self.assertIn('omitted',data['context_view'])


if __name__=='__main__':unittest.main()
