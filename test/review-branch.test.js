import test from 'node:test';
import assert from 'node:assert/strict';
import {createUserMessage} from '@deepseek-ai/dsh-llm';
import {reviewBranch,FINAL_REVIEW_INSTRUCTION,toolLimitInstruction} from '../src/review-branch.js';
import {configure} from '../src/index.js';
import {validateResult} from '../src/core.js';

const candidate='Kept every approved row.';
const refs=[{text:'Keep approved rows.'}];
const normal=()=>({assessment:'on-track',audit:['objective','scope','method'].map(dimension=>({
  dimension,status:'consistent',requirement:'Keep approved rows.',requirement_quotes:['Keep approved rows.'],
  updates:[],observed:candidate,evidence_quotes:[candidate]})),issues:[]});
async function* output(block,kind='stop',replayState) {
  yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind},...(replayState?{replayState}:{})};
}
const request=()=>({provider:'fixture',model:'script',messages:[createUserMessage({source:{kind:'user'},content:[{type:'text',text:refs[0].text}]})]});

test('nonliteral normal audit quotes are recorded as warnings, not discarded',()=>{
  const r=normal();r.audit[1].evidence_quotes=['Kept … approved rows'];r.audit[2].requirement_quotes=['Keep the approved rows'];
  const v=validateResult(JSON.stringify(r),candidate,refs,[]);
  assert.equal(v.reply.assessment,'on-track');assert.equal(v.warnings.length,2);
});

test('verification result stays in auxiliary history and opaque replay remains intact',async()=>{
  const req=request(),before=JSON.stringify(req),seen=[],records=[];let executions=0;
  const opaque={response:{opaque:'not-public'},blocks:[{}]};
  const stream=r=>{
    seen.push(r);
    if(seen.length===1)return output({type:'tool-call',id:'verify-1',name:'bash',arguments:'{"command":"check"}'},'tool-calls',opaque);
    assert.deepEqual(r.messages[1].source.replayState,opaque);
    assert.equal(r.messages[2].toolCallId,'verify-1');
    assert.equal(r.messages[2].content[0].text,'row count 86');
    const n=normal();n.audit[2].evidence_quotes=['row count 86'];
    return output({type:'text',text:JSON.stringify(n)});
  };
  const v=await reviewBranch({stream,request:req,candidate,refs,record:r=>records.push(r),executeTool:async()=>{
    executions++;return {isError:false,text:'row count 86'};
  }});
  assert.equal(v.status,'complete');assert.equal(v.reply.assessment,'on-track');assert.equal(executions,1);
  assert.equal(JSON.stringify(req),before,'actor prefix was not mutated');
  assert.equal(records.filter(r=>r.phase==='review_tool').length,1);
  assert(!JSON.stringify(records).includes('not-public'),'private replay state was not published');
});

test('a denied verification still yields a tool result and may conclude unknown',async()=>{
  let rounds=0;
  const v=await reviewBranch({request:request(),candidate,refs,executeTool:async()=>({isError:true,text:'Unavailable'}),
    stream:()=>++rounds===1?output({type:'tool-call',id:'denied',name:'write',arguments:'{}'},'tool-calls'):
      output({type:'text',text:JSON.stringify({...normal(),assessment:'unknown',audit:normal().audit.map(r=>({...r,status:'unresolved'}))})})});
  assert.equal(v.status,'complete');assert.equal(v.reply.assessment,'unknown');
});

test('tool budget bounds execution while returning results for every requested call',async()=>{
  let rounds=0,executions=0;
  async function* stream(r) {
    rounds++;
    if(rounds===1) {
      for(let i=0;i<4;i++)yield {type:'block-end',index:i,block:{type:'tool-call',id:'t'+i,name:'bash',arguments:'{}'}};
      yield {type:'finish',reason:{kind:'tool-calls'}};
    } else {
      assert.equal(r.messages.filter(m=>m.role==='tool').length,4);
      assert(r.messages.filter(m=>m.role==='tool').at(-1).isError);
      yield* output({type:'text',text:JSON.stringify(normal())});
    }
  }
  const v=await reviewBranch({request:request(),candidate,refs,stream,maxToolCalls:2,
    executeTool:async()=>{executions++;return {isError:false,text:'ok'};}});
  assert.equal(v.status,'complete');assert.equal(executions,2);
});

test('a missing terminal event does not silently become a normal review',async()=>{
  async function* stream(){yield {type:'block-end',index:0,block:{type:'text',text:JSON.stringify(normal())}};}
  const v=await reviewBranch({request:request(),candidate,refs,stream,executeTool:async()=>{throw Error('unused');}});
  assert.equal(v.reason,'missing_finish');
});

test('the last generation is explicitly reserved for a conclusion before the tool budget is silently exhausted',async()=>{
  let round=0;
  const v=await reviewBranch({request:request(),candidate,refs,maxRounds:3,maxToolCalls:3,
    executeTool:async()=>({isError:false,text:'verified'}),stream:r=>{
      round++;
      if(round<3)return output({type:'tool-call',id:'verify-'+round,name:'bash',arguments:'{}'},'tool-calls');
      assert.equal(r.messages.at(-1).content[0].text,FINAL_REVIEW_INSTRUCTION);
      assert.equal(r.messages.filter(m=>m.role==='tool').length,2);
      return output({type:'text',text:JSON.stringify(normal())});
    }});
  assert.equal(v.status,'complete');assert.equal(v.rounds,3);assert.equal(v.toolCalls,2);
});

test('defaults allow three sequential verifications plus one final conclusion',async()=>{
  let rounds=0,executions=0;const records=[];
  const config=configure();assert.equal(config.maxToolCalls,3);assert.equal(config.maxRounds,4);
  assert.equal(configure({maxToolCalls:5}).maxRounds,6);
  const v=await reviewBranch({request:request(),candidate,refs,record:r=>records.push(r),
    executeTool:async()=>({isError:++executions===2,text:'result-'+executions}),stream:r=>{
      rounds++;
      if(rounds<4)return output({type:'tool-call',id:'t'+rounds,name:'bash',arguments:'{}'},'tool-calls');
      assert.equal(r.messages.at(-1).content[0].text,toolLimitInstruction(3));
      const results=r.messages.filter(m=>m.role==='tool');assert.equal(results.length,3);
      assert.equal(results[2].content[0].text,'result-3','third result arrives before the final instruction');
      return output({type:'text',text:JSON.stringify(normal())});
    }});
  assert.equal(v.status,'complete');assert.equal(v.toolCalls,3);assert.equal(rounds,4);
  assert(records.some(r=>r.phase==='review_budget'&&r.reason==='tool_limit_reached'&&r.used===3));
});

test('only one conclusion generation follows an exhausted parallel tool budget',async()=>{
  let rounds=0,executions=0;
  async function* stream(){
    rounds++;
    for(let i=0;i<(rounds===1?3:1);i++)yield {type:'block-end',index:i,block:{type:'tool-call',id:'call-'+rounds+'-'+i,name:'bash',arguments:'{}'}};
    yield {type:'finish',reason:{kind:'tool-calls'}};
  }
  const v=await reviewBranch({request:request(),candidate,refs,stream,
    executeTool:async()=>{executions++;return {isError:false,text:'verified'};}});
  assert.equal(executions,3);assert.equal(rounds,2);
  assert.equal(v.status,'unreviewed');assert.equal(v.reason,'tool_requested_after_final_instruction');
});
