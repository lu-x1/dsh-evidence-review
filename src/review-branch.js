import { BlockAssembler, createToolResultMessage, createUserMessage } from '@deepseek-ai/dsh-llm';
import { publicHistory, publicText, validateResult } from './core.js';

export const FINAL_REVIEW_INSTRUCTION='This is the final review generation. No further tool turns are available. Use the evidence already collected to return the final JSON review now. Do not request tools. Choose unknown for any material uncertainty that remains unresolved.';
export const toolLimitInstruction=limit=>`The review tool-call limit (${limit}) has been reached. The tool results above are the last available verification results. Do not request any more tools. Return the final JSON review now, based on the evidence already collected: on-track, drift, or unknown. Choose unknown when material uncertainty remains; do not assume the task is correct.`;

export function conclusionInstruction(reached,limit,verifyDefinitions=false) {
  const original=reached?toolLimitInstruction(limit):FINAL_REVIEW_INSTRUCTION;
  return verifyDefinitions?original.replace('Choose unknown for any material uncertainty that remains unresolved.','Report drift if at least one supported conflict is established, even if another comparison is unresolved; otherwise choose unknown when a material uncertainty remains.').replace('Choose unknown when material uncertainty remains; do not assume the task is correct.','Report drift for at least one supported conflict; otherwise choose unknown when material uncertainty remains. Do not assume the task is correct.'):original;
}

// A short auxiliary conversation; only its public record and final notice are
// published. Original messages and adapter-private replay state remain intact.
export async function reviewBranch({stream,request,candidate,refs,executeTool,record=()=>{},maxToolCalls=3,maxRounds=maxToolCalls+1,window,verifyDefinitions=false}) {
  const messages=[...request.messages];let toolCalls=0,conclusionOnly=false;
  for(let round=1;round<=maxRounds;round++) {
    const assembler=new BlockAssembler();let sawFinish=false;
    for await(const chunk of stream({...request,messages:[...messages]})) {
      assembler.push(chunk);if(chunk.type==='finish')sawFinish=true;
    }
    const finish=assembler.finish.kind;
    record({phase:'review_round',round,finish,usage:assembler.usage,
      publicBlocks:assembler.blocks().filter(b=>b.type==='text'||b.type==='tool-call')});
    if(request.signal?.aborted||!sawFinish||!['stop','tool-calls'].includes(finish))
      return {status:'unreviewed',reason:request.signal?.aborted?'cancelled':!sawFinish?'missing_finish':`finish_${finish}`,toolCalls};
    const message=assembler.message({provider:request.provider,model:request.model,
      ...(assembler.replayState===undefined?{}:{replayState:assembler.replayState})});
    const calls=message.content.filter(b=>b.type==='tool-call');
    if(!calls.length) {
      const validation=validateResult(publicText(message.content),candidate,refs,publicHistory(messages),{window});
      return {status:'complete',...validation,toolCalls,rounds:round};
    }
    if(conclusionOnly)return {status:'unreviewed',reason:'tool_requested_after_final_instruction',toolCalls};
    if(round===maxRounds)return {status:'unreviewed',reason:'tool_round_limit',toolCalls};
    messages.push(message);
    for(const call of calls) {
      let result;
      if(toolCalls>=maxToolCalls)result={isError:true,text:'Review tool budget exhausted. Return your final review; use unknown when evidence remains insufficient.'};
      else {
        toolCalls++;
        try {result=await executeTool(call,request.signal);}
        catch(error){result={isError:true,text:`Verification could not run (${error.name}). Use available evidence or return unknown.`};}
      }
      messages.push(createToolResultMessage({callId:call.id,isError:result.isError,content:[{type:'text',text:result.text}]}));
      record({phase:'review_tool',round,call:{id:call.id,name:call.name,arguments:call.arguments},result});
    }
    if(toolCalls>=maxToolCalls||round===maxRounds-1) {
      const reached=toolCalls>=maxToolCalls;
      const instruction=conclusionInstruction(reached,maxToolCalls,verifyDefinitions);
      messages.push(createUserMessage({source:{kind:'dsh-evidence-review',form:'review-budget'},
        content:[{type:'text',text:instruction}]}));
      record({phase:'review_budget',round,used:toolCalls,limit:maxToolCalls,
        reason:reached?'tool_limit_reached':'last_generation',instruction});
      conclusionOnly=true;
    }
  }
  return {status:'unreviewed',reason:'review_round_limit',toolCalls};
}
