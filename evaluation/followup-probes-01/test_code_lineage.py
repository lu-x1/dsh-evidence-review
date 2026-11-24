import json
import unittest
import code_lineage as L


class LineageTests(unittest.TestCase):
    def messages(self):
        code="def rank(x):\n    return x.rank(pct=True)*100\nc['score']=0.5*c.raw+0.5*rank(c.share)\nc.to_pickle('out.pkl')\n"
        return [{'role':'user','content':"c['score']=correct_user_formula"},
            {'role':'assistant','reasoning_content':'NEVER_INDEX_PRIVATE_REASONING','tool_calls':[{'id':'one','function':{'name':'bash','arguments':json.dumps({'command':"python - <<'PY'\n"+code+'PY'})}}]}]

    def test_only_public_calls_and_exact_python_assignment_provenance(self):
        out=L.cue(self.messages(),'Report the score.','Check score.')
        self.assertNotIn('NEVER_INDEX_PRIVATE',json.dumps(out));self.assertNotIn('correct_user_formula',json.dumps(out))
        row=next(v for v in out['entries'] if v['field']=='score')
        self.assertEqual(row['code'],"c['score']=0.5*c.raw+0.5*rank(c.share)")
        self.assertIn('share',row['dependencies']);self.assertEqual(out['source_contexts'][0]['message_position'],1)
        self.assertIn("c.to_pickle('out.pkl')",out['source_contexts'][0]['artifact_operations'])

    def test_invalid_python_is_not_silently_claimed_parsed(self):
        m=[{'role':'assistant','tool_calls':[{'function':{'name':'python','arguments':json.dumps({'code':'invalid : : :'})}}]}]
        out=L.build_index(m);self.assertEqual(out['python_blocks_unparsed'],1);self.assertEqual(out['records'],[])

    def test_code_is_never_executed(self):
        m=[{'role':'assistant','tool_calls':[{'function':{'name':'python','arguments':json.dumps({'code':"raise RuntimeError('must not execute')\nx=1"})}}]}]
        self.assertEqual(L.build_index(m)['records'][0]['field'],'x')

    def test_distinct_redefinitions_are_kept_within_bound(self):
        m=[{'role':'assistant','tool_calls':[{'function':{'name':'python','arguments':json.dumps({'code':"x['score']=1\nx['score']=2"})}}]}]
        out=L.cue(m,'score','score',max_chars=4000)
        self.assertEqual(len([v for v in out['entries'] if v['field']=='score']),2)


    def test_transporting_latest_saved_field_keeps_its_original_calculation(self):
        m=[{'role':'assistant','tool_calls':[{'function':{'name':'python','arguments':json.dumps({'code':"c['score']=0.5*c.raw+0.5*c.share\na['score']=a.country.map(c.score)\nb['score']=b.country.map(c.score)\nz['score']=z.country.map(c.score)"})}}]}]
        out=L.cue(m,'score','score')
        self.assertTrue(any("0.5*c.raw" in r['code'] for r in out['entries']))


if __name__=='__main__':unittest.main()
