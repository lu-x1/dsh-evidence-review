import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {mkdtemp,writeFile,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {Context} from '@deepseek-ai/cordis';
import {SessionStore,SessionId} from '@deepseek-ai/dsh-session';
import {AgentRegistry} from '@deepseek-ai/dsh-agent';
import {AgentLoop} from '@deepseek-ai/dsh-agent-loop';
import {LlmRuntime,LlmAdapter,createUserMessage} from '@deepseek-ai/dsh-llm';
import {ToolRuntime} from '@deepseek-ai/dsh-tools';
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt';
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection';
import {publicText} from '../src/core.js';
import * as plugin from '../src/index.js';

test('native periodic check executes a read-only verification and keeps its exchange out of actor messages',async t=>{
  const cwd=await mkdtemp(join(tmpdir(),'dsh-native-review-'));t.after(()=>rm(cwd,{recursive:true,force:true}));
  await writeFile(join(cwd,'numbers.csv'),'x\n2\n3\n');
  const ctx=new Context();t.after(()=>ctx.fiber.dispose());const load=p=>ctx.plugin(p).await();
  for(const p of [SessionStore,SessionProjectionRegistry,SystemPrompt,ToolRuntime])await load(p);
  await load(await import('@deepseek-ai/dsh-tool-executor-native'));await load(AgentRegistry);await load(LlmRuntime);
  await ctx.plugin(AgentLoop,{agents:[],maxParallelToolCalls:1}).await();
  await ctx.plugin(plugin,{every:2,timeoutMs:10000}).await();
  let actorSteps=0,reviewRounds=0,actorTools=0;const actors=[];
  for(const name of ['noop','bash'])ctx.tools.register({name,description:name,
    parameters:{type:'object',properties:{command:{type:'string'}},required:['command']},
    output:{schema:{type:'object'},render:()=>[{type:'text',text:'actor tool done'}]},
    execute:async()=>{assert.equal(name,'noop','review tool reached actor executor');actorTools++;return {};}});
  ctx.llm.registerAdapter(['fixture'],new class extends LlmAdapter {
    async *stream(req){
      let block,finish;
      if(req.purpose==='evidence-review'){
        reviewRounds++;
        const source=actors.at(-1);assert.deepEqual(req.messages.slice(0,source.messages.length),source.messages);
        const text=publicText(req.messages[source.messages.length].content);
        const candidate=JSON.parse(text.slice(text.indexOf('\n\n')+2)).candidate;
        if(reviewRounds===1){
          block={type:'tool-call',id:'actual-verification',name:'bash',arguments:JSON.stringify({command:
            "/usr/bin/python3 -c \"import csv; print('verification-only-marker',sum(int(r['x']) for r in csv.DictReader(open('numbers.csv'))))\""})};finish='tool-calls';
        }else{
          const result=req.messages.find(m=>m.role==='tool'&&m.toolCallId==='actual-verification');
          assert(result);assert.match(publicText(result.content),/verification-only-marker 5/);
          block={type:'text',text:JSON.stringify({assessment:'on-track',audit:['objective','scope','method'].map(dimension=>({
            dimension,requirement:'Keep all rows.',requirement_quotes:['Keep all rows.'],updates:[],
            observed:candidate,evidence_quotes:[candidate],status:'consistent'})),issues:[]})};finish='stop';
        }
      }else{
        actors.push(req);actorSteps++;
        assert(!JSON.stringify(req.messages).includes('verification-only-marker'),'review transcript leaked into actor messages');
        block=actorSteps<3?{type:'tool-call',id:randomUUID(),name:'noop',arguments:'{"command":"keep all rows"}'}:{type:'text',text:'Done.'};
        finish=actorSteps<3?'tool-calls':'stop';
      }
      yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:finish}};
    }
  }());
  const handle=await ctx.agents.create({sessionId:SessionId(randomUUID()),meta:{cwd},agentOptions:{provider:'fixture',model:'script'}});
  handle.agent.followup(createUserMessage({source:{kind:'user'},content:[{type:'text',text:'Keep all rows.'}]}));
  await handle.agent.whenIdle();
  assert.equal(actorSteps,3);assert.equal(reviewRounds,2);assert.equal(actorTools,2);
  const rows=handle.agent.session.snapshotEvents().filter(e=>e.type===plugin.RECORD_TYPE).map(e=>e.data);
  assert(rows.some(r=>r.phase==='review_tool'&&!r.result.isError));assert(rows.some(r=>r.phase==='result'&&r.reply.assessment==='on-track'));
  assert.equal(await readFile(join(cwd,'numbers.csv'),'utf8'),'x\n2\n3\n');
});
