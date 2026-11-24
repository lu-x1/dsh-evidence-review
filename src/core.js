import { createHash } from 'node:crypto';
import { tail as protocolTail, validate } from './protocol.js';
export { RULES } from './protocol.js';
export const digest=text=>createHash('sha256').update(text).digest('hex');
export function publicText(content) {
  if(typeof content==='string')return content;
  if(!Array.isArray(content))return '';
  return content.filter(b=>b?.type==='text').map(b=>typeof b.text==='string'?b.text:'').join('');
}
export function candidateBlock(block) {
  if(block?.type==='text')return typeof block.text==='string'?block.text:'';
  if(block?.type==='tool-call')return `Proposed tool ${block.name} (${block.id}):\n${block.arguments}`;
  return '';
}
export function requirements(messages,events) {
  // Projections may lose metadata: authenticate user texts with native sources.
  const actual=new Set(events.filter(e=>e.type==='user/message'&&e.data.source?.kind==='user').map(e=>publicText(e.data.content)));
  return messages.flatMap((m,i)=>m.role==='user'&&actual.has(publicText(m.content))?[{id:`m${i}`,text:publicText(m.content)}]:[]);
}
export function publicHistory(messages) {
  return messages.flatMap(m=>{
    const blocks=typeof m.content==='string'?[{type:'text',text:m.content}]:m.content;
    const text=(blocks??[]).map(candidateBlock).filter(Boolean).join('\n\n');
    return text?[{role:m.role,text}]:[];
  });
}
export const tail=(candidate,refs,options={})=>protocolTail(candidate,'audit1',refs,options);
export const validateReply=(text,candidate,refs,history)=>validate(text,candidate,refs,history,'audit1').reply;
export const validateResult=(text,candidate,refs,history,options={})=>validate(text,candidate,refs,history,'audit1',options);
export function noticeText(issue) {
  return 'Periodic evidence review — possible conflict; verify the effective user requirements.\n'+
    `Candidate: ${issue.candidate_quote}\nUser requirements:\n${issue.requirement_quotes.map(q=>'- '+q).join('\n')}\n`+
    `Concern: ${issue.diagnosis}\nCheck: ${issue.reminder}`;
}
export const latestUserEpoch=events=>events.findLast(e=>e.type==='user/message'&&e.data.source?.kind==='user')?.seq??0;

// Bound the newly executed interval without rewriting the actor request prefix.
export function checkpointWindow(messages,candidate,ordinal,every,previous) {
  const rows=messages.map((m,index)=>({index,role:m.role,text:publicHistory([m])[0]?.text??''}));
  const priorOrdinal=previous?.ordinal??Math.max(0,Math.floor((ordinal-1)/every)*every);
  let start=-1,boundary='matched_previous_checkpoint';
  if(previous?.candidateSha256) {
    const actors=rows.filter(r=>r.role==='assistant');
    const expected=actors[actors.length-(ordinal-priorOrdinal-1)-1];
    if(expected&&digest(expected.text)===previous.candidateSha256)start=expected.index+1;
    else {
      const matches=actors.filter(r=>digest(r.text)===previous.candidateSha256);
      if(matches.length===1){start=matches[0].index+1;boundary='matched_checkpoint_retained_count_changed';}
    }
  }
  if(start<0) {
    const needed=Math.max(0,ordinal-priorOrdinal-1);
    const actors=rows.filter(r=>r.role==='assistant');
    start=needed?actors[Math.max(0,actors.length-needed)]?.index??rows.length:rows.length;
    boundary=previous?'previous_checkpoint_missing_fallback_retained_tail':actors.length>=needed?'initial_retained_tail':'initial_prefix_incomplete';
  }
  return {start_ordinal:priorOrdinal+1,end_ordinal:ordinal,boundary,
    entries:rows.slice(start).filter(r=>r.text&&['assistant','tool','user'].includes(r.role)),
    current_candidate:candidate};
}
