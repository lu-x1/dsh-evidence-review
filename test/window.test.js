import test from 'node:test';
import assert from 'node:assert/strict';
import {checkpointWindow,digest,tail,validateResult} from '../src/core.js';
import {conclusionInstruction} from '../src/review-branch.js';

test('checkpoint boundary excludes previous interval and retains intervening observations',()=>{
  const messages=[{role:'user',content:'Keep all rows.'},{role:'assistant',content:'old checkpoint'},
    {role:'assistant',content:'dropped rows'},{role:'tool',content:'saved 2 rows'},
    {role:'user',content:'Now draw the result.'},{role:'assistant',content:'drawing'}];
  const w=checkpointWindow(messages,'finished drawing',5,3,{ordinal:2,candidateSha256:digest('old checkpoint')});
  assert.equal(w.boundary,'matched_previous_checkpoint');
  assert.deepEqual(w.entries.map(e=>e.text),['dropped rows','saved 2 rows','Now draw the result.','drawing']);
  assert.equal(w.start_ordinal,3);assert.equal(w.end_ordinal,5);
});

test('missing boundary and compacted prefix are explicitly marked rather than claimed complete',()=>{
  const m=[{role:'assistant',content:'only retained action'}];
  assert.equal(checkpointWindow(m,'current',16,8,{ordinal:8,candidateSha256:'absent'}).boundary,
    'previous_checkpoint_missing_fallback_retained_tail');
  assert.equal(checkpointWindow(m,'current',8,8).boundary,'initial_prefix_incomplete');
  assert.equal(checkpointWindow([], 'first',1,8).entries.length,0);
});

test('issue can cite an interval action or observation but cannot cite arbitrary older history or user text',()=>{
  const refs=[{text:'Keep all rows.'}],history=[{role:'assistant',text:'old unrelated mistake'}];
  const window={entries:[{role:'assistant',text:'drop required rows'},{role:'tool',text:'saved 2 rows'},
    {role:'user',text:'an instruction is not an action'}]};
  const issue={candidate_quote:'drop required rows',requirement_quotes:['Keep all rows.'],diagnosis:'Rows lost.',reminder:'Rebuild without dropping rows.'};
  const reply={assessment:'drift',audit:['objective','scope','method'].map(dimension=>({dimension,
    requirement:'Keep all rows.',requirement_quotes:['Keep all rows.'],updates:[],observed:'rows lost',
    evidence_quotes:['drop required rows'],status:dimension==='scope'?'conflict':'unresolved'})),issues:[issue]};
  const check=()=>validateResult(JSON.stringify(reply),'Drawing now.',refs,history,{window});
  assert.doesNotThrow(check);
  assert.throws(()=>validateResult(JSON.stringify(reply),'Drawing now.',refs,history),/candidate_quote/);
  issue.candidate_quote='saved 2 rows';assert.doesNotThrow(check);
  for(const text of ['old unrelated mistake','an instruction is not an action']) {
    issue.candidate_quote=text;assert.throws(check,/candidate_quote/);
  }
});

test('definition treatment changes only its instructions; original users and candidate are preserved',()=>{
  const refs=[{text:'Original formula. Later local exception.'}],candidate='The current output';
  const split=x=>{const n=x.indexOf('\n\n');return [x.slice(0,n),JSON.parse(x.slice(n+2))];};
  const [a,x]=split(tail(candidate,refs)),[b,y]=split(tail(candidate,refs,{verifyDefinitions:true}));
  assert.deepEqual(x,y);assert(!a.includes('small discriminating example'));assert(b.includes('small discriminating example'));
  assert(conclusionInstruction(true,3,true).includes('at least one supported conflict'));
  assert(!conclusionInstruction(false,3,true).includes('unknown for any material uncertainty'));
  assert(conclusionInstruction(false,3,false).includes('unknown for any material uncertainty'));
});

test('repeated public outputs do not move the checkpoint forward and hide new actions',()=>{
  const m=[{role:'assistant',content:'same'}, {role:'assistant',content:'bad action'},
    {role:'assistant',content:'same'}];
  const w=checkpointWindow(m,'current',4,3,{ordinal:1,candidateSha256:digest('same')});
  assert(w.entries.some(r=>r.text==='bad action'));
  assert.equal(w.boundary,'matched_previous_checkpoint');
});
