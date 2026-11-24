import test from 'node:test';
import assert from 'node:assert/strict';
import {validate,tail} from '../src/protocol.js';
const refs=[{text:'Analyze approved records. Keep the metric.'}],history=[{text:'The script selected all records.'}];
const candidate='select all records';
const issue={candidate_quote:'all records',requirement_quotes:['Analyze approved records.'],diagnosis:'Scope expands.',reminder:'Check the approved filter.'};
function row(dimension,status='consistent') {return {dimension,status,requirement:'approved records',requirement_quotes:['Analyze approved records.'],updates:[],observed:'select all records',evidence_quotes:['select all records']};}
const reply={assessment:'drift',audit:[row('objective'),row('scope','conflict'),row('method')],issues:[issue]};
test('same supported conflict works with one or three allowed issues',()=>{
  for(const mode of ['spot1','spot3','audit1','audit3'])assert.equal(validate(JSON.stringify(reply),candidate,refs,history,mode).reply.assessment,'drift');
});
test('normal requires evidence coverage in audit modes; unresolved is not a pass',()=>{
  const r={assessment:'on-track',audit:[],issues:[]};
  assert.doesNotThrow(()=>validate(JSON.stringify(r),candidate,refs,history,'spot1'));
  assert.throws(()=>validate(JSON.stringify(r),candidate,refs,history,'audit1'),/audit_coverage/);
  r.audit=[row('objective'),row('scope','unresolved'),row('method')];
  assert.throws(()=>validate(JSON.stringify(r),candidate,refs,history,'audit1'),/unresolved_pass/);
  r.assessment='unknown';assert.doesNotThrow(()=>validate(JSON.stringify(r),candidate,refs,history,'audit1'));
});
test('multiple issues cannot bypass evidence checks or configured issue cap',()=>{
  const r={...reply,issues:[issue,issue]};
  assert.throws(()=>validate(JSON.stringify(r),candidate,refs,history,'audit1'),/arrays_or_issue_limit/);
  assert.doesNotThrow(()=>validate(JSON.stringify(r),candidate,refs,history,'audit3'));
  r.issues[1]={...issue,requirement_quotes:['invented requirement']};
  assert.throws(()=>validate(JSON.stringify(r),candidate,refs,history,'audit3'),/issue_user_quotes/);
});
test('spot and audit share schema; cardinality changes only the limit value',()=>{
  const split=mode=>tail(candidate,mode).split('\n\n');
  const a=split('spot1'),b=split('spot3');assert.equal(a[0],b[0]);
  const x=JSON.parse(a[1]),y=JSON.parse(b[1]);delete x.issue_limit;delete y.issue_limit;assert.deepEqual(x,y);
});
test('a whole-document JSON code fence preserves the review judgment',()=>{
  const normal={assessment:'on-track',audit:[row('objective'),row('scope'),row('method')],issues:[]};
  for(const label of ['json','']) {
    const wrapped='```'+label+'\n'+JSON.stringify(normal)+'\n```';
    assert.deepEqual(validate(wrapped,candidate,refs,history,'audit1').reply,normal);
  }
});
test('code-fence compatibility does not extract judgments from prose or multiple blocks',()=>{
  const block='```json\n'+JSON.stringify(reply)+'\n```';
  for(const text of ['Here is the verdict:\n'+block,block+'\nDone.',block+'\n'+block,
                     '```python\n'+JSON.stringify(reply)+'\n```'])
    assert.throws(()=>validate(text,candidate,refs,history,'audit1'),SyntaxError);
});
test('a fenced review still needs genuine issue evidence and the existing schema',()=>{
  const forged={...reply,issues:[{...issue,requirement_quotes:['invented requirement']}]};
  assert.throws(()=>validate('```json\n'+JSON.stringify(forged)+'\n```',candidate,refs,history,'audit1'),/issue_user_quotes/);
  assert.throws(()=>validate('```json\n'+JSON.stringify({assessment:'on-track'})+'\n```',candidate,refs,history,'audit1'),/fields/);
});
