import assert from 'node:assert/strict';
import { createUserMessage, isAgentLoopRequest } from '@deepseek-ai/dsh-llm';
import { appendPluginRecord } from '@deepseek-ai/dsh-session';
import { candidateBlock, checkpointWindow, digest, latestUserEpoch, noticeText, requirements, tail } from './core.js';
import { reviewBranch } from './review-branch.js';
import { createReadOnlyExecutor } from './review-tools.js';

export const name = 'dsh-evidence-review';
export const inject = ['agents','sessions','llm'];
export const RECORD_TYPE = 'plugin:dsh-evidence-review/receipt';

export function configure(input={}) {
  const config={ every:8, maxTokens:16384, timeoutMs:120000, maxToolCalls:3, maxRounds:(input.maxToolCalls??3)+1, toolTimeoutMs:15000, pythonExecutable:'/usr/bin/python3', reviewScope:'current', verifyDefinitions:false, ...input };
  assert(Object.keys(config).every(k => ['every','maxTokens','timeoutMs','maxToolCalls','maxRounds','toolTimeoutMs','pythonExecutable','reviewScope','verifyDefinitions'].includes(k)), 'unknown_config');
  for (const [key,value] of Object.entries(config)) {
    if(key==='reviewScope')assert(['current','interval'].includes(value),'invalid_reviewScope');
    else if(key==='verifyDefinitions')assert(typeof value==='boolean','invalid_verifyDefinitions');
    else if(key==='pythonExecutable')assert(typeof value==='string'&&value.startsWith('/'),'invalid_pythonExecutable');
    else assert(Number.isSafeInteger(value) && value > 0, `invalid_${key}`);
  }
  return Object.freeze(config);
}

export function apply(ctx,input={}) {
  const config=configure(input), disposed=new AbortController(), agents=new Map();
  ctx.effect(() => () => { disposed.abort(); agents.clear(); });
  function record(state,row) {
    // Public receipt fields only. Omit absent optional usage before the native
    // session's strict lossless-JSON validation; never serialize request bodies.
    appendPluginRecord(state.agent.session,RECORD_TYPE,JSON.parse(JSON.stringify({version:1,...row})));
  }
  ctx.on('agent/created',({agent}) => {
    const rows=agent.session.snapshotEvents().filter(e => e.type===RECORD_TYPE).map(e => e.data);
    agents.set(agent.session.id,{ agent, ordinal:Math.max(0,...rows.map(r => r.ordinal ?? 0)),
      lastCheckpoint:rows.findLast(r=>r.phase==='window_boundary'||(r.phase==='check'&&r.candidateSha256)),
      sent:new Set(rows.filter(r => r.phase==='delivery').map(r => r.key)) });
  });
  ctx.on('llm/stream',(options,next) => {
    if (!isAgentLoopRequest(options) || disposed.signal.aborted) return next();
    const state=agents.get(options.sessionId);
    if (!state) return next();
    const sourceEpoch=latestUserEpoch(state.agent.session.snapshotEvents());
    const stream=next();
    return (async function* () {
      const blocks=new Map(); let reason;
      for await (const chunk of stream) {
        if (chunk.type==='block-end') {
          const text=candidateBlock(chunk.block); if (text) blocks.set(chunk.index,text);
        }
        if (chunk.type==='finish') reason=chunk.reason.kind;
        yield chunk;
      }
      if (!['stop','tool-calls'].includes(reason) || disposed.signal.aborted) return;
      const ordinal=++state.ordinal;
      record(state,{phase:'step',ordinal,sourceEpoch,finishReason:reason});
      if (ordinal % config.every !== 0) return;
      const candidate=[...blocks].sort((a,b)=>a[0]-b[0]).map(x=>x[1]).join('\n\n');
      if (!candidate.trim()) { record(state,{phase:'unreviewed',ordinal,reason:'no_public_candidate'});return; }
      const window=config.reviewScope==='interval'?checkpointWindow(options.messages,candidate,ordinal,config.every,state.lastCheckpoint):undefined;
      state.lastCheckpoint={ordinal,candidateSha256:digest(candidate)};
      record(state,{phase:'window_boundary',...state.lastCheckpoint});
      const refs=requirements(options.messages,state.agent.session.snapshotEvents());
      if (!refs.length) { record(state,{phase:'unreviewed',ordinal,reason:'no_authenticated_user_requirements'});return; }
      const signal=AbortSignal.any([...(options.signal?[options.signal]:[]),disposed.signal,AbortSignal.timeout(config.timeoutMs)]);
      // Original messages and adapter-private replay state stay opaque and on
      // their original route. Appending a new user message does not mutate them.
      const review={...options, messages:[...options.messages,createUserMessage({
        source:{kind:name,form:'review-request'},content:[{type:'text',text:tail(candidate,refs,{window,verifyDefinitions:config.verifyDefinitions})}]})],
        maxTokens:config.maxTokens,signal,purpose:'evidence-review'};
      assert(!isAgentLoopRequest(review), 'review_marked_as_actor');
      record(state,{phase:'check',ordinal,sourceEpoch,candidateSha256:digest(candidate),
        messageCount:options.messages.length,provider:options.provider,model:options.model,
        mode:'same_adapter_prefix_audit1_soft_audit_quotes_bounded_readonly_tools',reviewScope:config.reviewScope,verifyDefinitions:config.verifyDefinitions,window:window?{start:window.start_ordinal,end:window.end_ordinal,boundary:window.boundary}:undefined});
      try {
        const cwd=ctx.get('workingDirectory')?.get(state.agent.session)??state.agent.session.header.cwd;
        const outcome=await reviewBranch({stream:r=>ctx.llm.stream(r),request:review,candidate,refs,
          executeTool:createReadOnlyExecutor({cwd,pythonExecutable:config.pythonExecutable,toolTimeoutMs:config.toolTimeoutMs}),
          record:row=>record(state,{ordinal,sourceEpoch,...row}),maxToolCalls:config.maxToolCalls,maxRounds:config.maxRounds,window,verifyDefinitions:config.verifyDefinitions});
        if(outcome.status!=='complete') {record(state,{phase:'unreviewed',ordinal,...outcome});return;}
        const parsed=outcome.reply;
        record(state,{phase:'result',ordinal,sourceEpoch,reply:parsed,warnings:outcome.warnings,toolCalls:outcome.toolCalls,semanticVerified:false});
        if (parsed.assessment!=='drift') return;
        const events=state.agent.session.snapshotEvents();
        if (latestUserEpoch(events)!==sourceEpoch || state.agent.inbox.nextStep.some(m=>m.role==='user'&&m.source?.kind==='user')) {
          record(state,{phase:'delivery_skipped',ordinal,reason:'user_updated'});return;
        }
        const issue=parsed.issues[0];
        const key=digest(JSON.stringify([sourceEpoch,issue.candidate_quote,issue.requirement_quotes]));
        if (state.sent.has(key)) { record(state,{phase:'delivery_skipped',ordinal,reason:'duplicate'});return; }
        const text=noticeText(issue);
        state.agent.inject(createUserMessage({source:{kind:name,form:'notice'},content:[{type:'text',text}]}));
        state.sent.add(key);record(state,{phase:'delivery',ordinal,sourceEpoch,key,text,status:'enqueued_not_yet_proven_consumed'});
      } catch (error) {
        record(state,{phase:'unreviewed',ordinal,reason:'review_failed',errorClass:error?.name ?? 'Error'});
      }
    })();
  });
}
