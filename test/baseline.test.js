import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { Context } from '@deepseek-ai/cordis';
import { SessionStore, SessionId, appendPluginRecord } from '@deepseek-ai/dsh-session';
import { AgentRegistry } from '@deepseek-ai/dsh-agent';
import { AgentLoop } from '@deepseek-ai/dsh-agent-loop';
import { LlmRuntime, LlmAdapter, createUserMessage, isAgentLoopRequest } from '@deepseek-ai/dsh-llm';
import { ToolRuntime } from '@deepseek-ai/dsh-tools';
import { SystemPrompt } from '@deepseek-ai/dsh-system-prompt';
import { SessionProjectionRegistry } from '@deepseek-ai/dsh-session-projection';
import * as plugin from '../src/index.js';
import { publicText, requirements, tail, validateReply, candidateBlock } from '../src/core.js';

test('public projection does not inspect private blocks; exact references required',()=>{
  const privateBlock={type:'reasoning',get text(){throw Error('private text accessed');}};
  assert.equal(publicText([privateBlock,{type:'text',text:'public'}]),'public');
  assert.equal(candidateBlock(privateBlock),'');
  const refs=[{id:'m0',text:'Keep all rows.'}],r=reviewReply('drop rows',true);
  assert.deepEqual(validateReply(JSON.stringify(r),'drop rows',refs,[]),r);
  assert.throws(()=>validateReply(JSON.stringify({...r,issues:[{...r.issues[0],requirement_quotes:['invented']}]}),'drop rows',refs,[]));
  assert.throws(()=>validateReply(JSON.stringify({...r,issues:[{...r.issues[0],candidate_quote:'invented'}]}),'drop rows',refs,[]));
  assert.equal(requirements([{role:'user',content:'old notice'}],[{type:'user/message',data:{source:{kind:plugin.name},content:'old notice'}}]).length,0);
});

function reviewReply(candidate,bad,invalid=false) {
  return {assessment:bad?'drift':'on-track',audit:['objective','scope','method'].map(dimension=>({
    dimension,status:bad&&dimension==='scope'?'conflict':'consistent',requirement:'Keep all rows.',
    requirement_quotes:['Keep all rows.'],updates:[],observed:candidate,evidence_quotes:[candidate]})),
    issues:bad?[{candidate_quote:invalid?'invented':candidate,requirement_quotes:['Keep all rows.'],
      diagnosis:'The candidate removes required rows.',reminder:'Restore the required rows.'}]:[]};
}

async function fixture(t,mode='normal',every=2,{priorOrdinal=0,steps=112}={}) {
  const ctx=new Context();t.after(()=>ctx.fiber.dispose());
  const load=(p,c)=>ctx.plugin(p,c).await();
  await load(SessionStore);await load(SessionProjectionRegistry);await load(SystemPrompt);await load(ToolRuntime);
  await load(await import('@deepseek-ai/dsh-tool-executor-native'));
  await load(AgentRegistry);await load(LlmRuntime);
  await ctx.plugin(AgentLoop,{agents:[],maxParallelToolCalls:1}).await();
  await ctx.plugin(plugin,mode==='long'?{timeoutMs:1000}:{every,timeoutMs:1000,...(mode==='interval'?{reviewScope:'interval'}:{})});
  const executed=[],seen=[],reviews=[];let step=0,agent;
  ctx.tools.register({name:'noop',description:'Record a string without executing it',
    parameters:{type:'object',properties:{command:{type:'string'}},required:['command']},
    output:{schema:{type:'object',properties:{ok:{type:'boolean'}},required:['ok']},render:()=>[{type:'text',text:'recorded'}]},
    async execute(args){executed.push(args.command);return {ok:true};}});
  const adapter=new class extends LlmAdapter {
    async *stream(req) {
      let block,finish;
      if (req.purpose==='evidence-review') {
        reviews.push(req);assert(!isAgentLoopRequest(req));
        const source=seen.at(-1);
        assert.deepEqual(req.messages.slice(0,source.messages.length),source.messages);assert.deepEqual(req.tools,source.tools);
        assert.equal(req.provider,source.provider);assert.equal(req.model,source.model);
        assert.equal(req.reasoningEffort,source.reasoningEffort);
        assert.equal(req.maxTokens,16384);
        const text=publicText(req.messages[source.messages.length].content),data=JSON.parse(text.slice(text.indexOf('\n\n')+2));
        if (mode==='stale') agent.steer(createUserMessage({source:{kind:'user'},content:[{type:'text',text:'Now a new task.'}]}));
        if (mode==='tool') {
          block={type:'tool-call',id:randomUUID(),name:'noop',arguments:JSON.stringify({command:'reviewer_should_never_execute'})};
          finish='tool-calls';
        } else {
          const bad=mode==='interval'?data.review_window.entries.some(e=>e.text.includes('drop_required_rows')):data.candidate.includes('drop_required_rows');
          const r=reviewReply(mode==='interval'&&bad?'drop_required_rows':data.candidate,bad,mode==='invalid');
          block={type:'text',text:mode==='length'?'{':JSON.stringify(r)};
          finish=mode==='length'?'length':mode==='error'?'error':'stop';
        }
      } else {
        assert(isAgentLoopRequest(req));seen.push(req);step++;
        const notices=req.messages.filter(m=>m.source?.kind===plugin.name);
        if (step===3 && mode==='normal' && every===2) assert.equal(notices.length,1,'notice reached actual next actor input');
        const ordinal=priorOrdinal+step;
        if (mode==='long' && ordinal===105) assert.equal(notices.length,1,'late reminder reached actual next actor input');
        const command=mode==='interval'?(step===1?'keep_all_rows':step===2?'drop_required_rows':step===3?'inspect_plot':step===4?'render_summary':null):mode==='long'
          ? step===steps?null:ordinal===104?'drop_required_rows':ordinal===105?'restore_rows':'keep_all_rows'
          : step===1?'keep_all_rows':step===2?'drop_required_rows':
            step===3&&mode==='normal'&&every===2?'restore_rows':null;
        block=command?{type:'tool-call',id:randomUUID(),name:'noop',arguments:JSON.stringify({command})}
          :{type:'text',text:'Completed.'};finish=command?'tool-calls':'stop';
        assert(step<=(mode==='long'?steps:mode==='interval'?5:4),'unbounded actor loop');
      }
      yield {type:'block-start',index:0,blockType:block.type};
      yield {type:'block-end',index:0,block};
      yield {type:'finish',reason:{kind:finish}};
    }
  }();
  ctx.llm.registerAdapter(['fixture'],adapter);
  const handle=await ctx.agents.create({sessionId:SessionId(randomUUID()),agentOptions:{provider:'fixture',model:'script'},
    setup(_ctx,agent) {
      // Restore public monitor receipts before agent/created reconstructs its
      // state. No actor history or paid endpoint is needed for this lifecycle test.
      for(let ordinal=1;ordinal<=priorOrdinal;ordinal++) {
        appendPluginRecord(agent.session,plugin.RECORD_TYPE,{version:1,phase:'step',ordinal});
        if(ordinal%8===0) appendPluginRecord(agent.session,plugin.RECORD_TYPE,{version:1,phase:'check',ordinal});
      }
    }});
  agent=handle.agent;agent.followup(createUserMessage({source:{kind:'user'},content:[{type:'text',text:'Keep all rows.'}]}));
  await agent.whenIdle();
  return {seen,reviews,executed,rows:agent.session.snapshotEvents().filter(e=>e.type===plugin.RECORD_TYPE).map(e=>e.data)};
}

test('native loop: periodic review, next-step notice, repair and continued normal checks',async t=>{
  const f=await fixture(t);
  assert.equal(f.seen.length,4,JSON.stringify(f.rows));assert.equal(f.reviews.length,2);
  assert.deepEqual(f.rows.filter(r=>r.phase==='check').map(r=>r.ordinal),[2,4]);
  assert.equal(f.rows.filter(r=>r.phase==='delivery').length,1);
  assert.deepEqual(f.executed,['keep_all_rows','drop_required_rows','restore_rows']);
});

for(const mode of ['tool','length','invalid','error','stale']) test(`native loop: ${mode} cannot become a successful review or execute reviewer tools`,async t=>{
  const f=await fixture(t,mode);
  assert.equal(f.reviews.length,mode==='tool'?4:1);assert.equal(f.rows.filter(r=>r.phase==='delivery').length,0);
  assert(!f.executed.includes('reviewer_should_never_execute'));
  if (mode==='stale') assert(f.rows.some(r=>r.phase==='delivery_skipped'&&r.reason==='user_updated'));
  else {
    const expected={tool:'tool_requested_after_final_instruction',length:'finish_length',invalid:'review_failed',error:'finish_error'}[mode];
    assert(f.rows.some(r=>r.phase==='unreviewed'&&r.reason===expected),JSON.stringify(f.rows));
  }
});

test('no forced final review between scheduled steps',async t=>{
  const f=await fixture(t,'normal',8);
  assert.equal(f.reviews.length,0);assert.equal(f.rows.filter(r=>r.phase==='step').length,3);
});

test('default cadence continues past twelve checks and delivers a late repair notice',async t=>{
  const f=await fixture(t,'long');
  assert.equal(f.seen.length,112);
  assert.equal(f.reviews.length,14);
  assert.deepEqual(f.rows.filter(r=>r.phase==='check').map(r=>r.ordinal),Array.from({length:14},(_,i)=>(i+1)*8));
  assert(f.rows.some(r=>r.phase==='delivery'&&r.ordinal===104));
  assert(f.executed.includes('restore_rows'));
  assert(!f.rows.some(r=>r.reason==='check_cap'));
});

test('restored monitor receipts retain cadence after twelve previous checks',async t=>{
  const f=await fixture(t,'long',8,{priorOrdinal:100,steps:12});
  assert.equal(f.reviews.length,2);
  assert.deepEqual(f.rows.filter(r=>r.phase==='step'&&r.ordinal>100).map(r=>r.ordinal),Array.from({length:12},(_,i)=>101+i));
  assert.deepEqual(f.rows.filter(r=>r.phase==='check'&&r.ordinal>100).map(r=>r.ordinal),[104,112]);
  assert(f.rows.some(r=>r.phase==='delivery'&&r.ordinal===104));
  assert(!f.rows.some(r=>r.reason==='check_cap'));
});

test('obsolete session cap cannot silently re-enable a limit',()=>{
  assert.throws(()=>plugin.configure({maxChecks:12}),/unknown_config/);
});

// Earlier actor action is the issue; the checkpoint's own output is benign.
test('interval review delivers a supported earlier-action reminder to the next real actor request',async t=>{
  const f=await fixture(t,'interval',4);
  assert.equal(f.reviews.length,1);
  const data=JSON.parse(publicText(f.reviews[0].messages.at(-1).content).split('\n\n').at(-1));
  assert(!data.candidate.includes('drop_required_rows'));
  assert(data.review_window.entries.some(e=>e.role==='assistant'&&e.text.includes('drop_required_rows')));
  assert.equal(f.rows.filter(r=>r.phase==='delivery').length,1);
  assert(f.seen[4].messages.some(m=>m.source?.kind===plugin.name&&publicText(m.content).includes('drop_required_rows')));
});
