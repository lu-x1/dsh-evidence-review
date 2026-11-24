import test from 'node:test';
import assert from 'node:assert/strict';
import {requirements,tail} from '../src/core.js';

test('review tail repeats only authenticated original users in order and without clipping',()=>{
  const first='Keep the complete analysis universe. '+ 'x'.repeat(240) +' The threshold remains unchanged.';
  const last='Apply the current sensitivity check.';
  const note='Generated reminder: use four units.';
  const messages=[{role:'user',content:first},{role:'user',content:note},{role:'user',content:last}];
  const events=[{type:'user/message',data:{source:{kind:'user'},content:first}},
    {type:'user/message',data:{source:{kind:'dsh-evidence-review'},content:note}},
    {type:'user/message',data:{source:{kind:'user'},content:last}}];
  const refs=requirements(messages,events);
  const value=JSON.parse(tail('candidate',refs).split('\n\n')[1]);
  assert.deepEqual(value.original_user_messages,[first,last]);
  assert(!value.original_user_messages.includes(note));
  assert(value.original_user_messages[0].endsWith('The threshold remains unchanged.'));
  assert(!('reference_directory' in value));
});
