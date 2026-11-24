import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createReadOnlyExecutor} from '../src/review-tools.js';

test('real verifier can calculate, cannot write task files, and may write temporary output',async t=>{
  const cwd=await mkdtemp(join(tmpdir(),'dsh-review-tools-'));t.after(()=>rm(cwd,{recursive:true,force:true}));
  await writeFile(join(cwd,'numbers.csv'),'x\n2\n3\n');
  const run=createReadOnlyExecutor({cwd});
  const result=await run({name:'bash',arguments:JSON.stringify({command:"/usr/bin/python3 - <<'PY'\nimport csv,pathlib\nprint(sum(int(r['x']) for r in csv.DictReader(open('numbers.csv'))))\ntry: pathlib.Path('numbers.csv').write_text('bad')\nexcept OSError: print('task write denied')\npathlib.Path('/tmp/verification.txt').write_text('scratch allowed')\nprint(pathlib.Path('/tmp/verification.txt').read_text())\nPY"})});
  assert.equal(result.isError,false,result.text);assert.match(result.text,/5\ntask write denied\nscratch allowed/);
  assert.equal(await readFile(join(cwd,'numbers.csv'),'utf8'),'x\n2\n3\n');
});

test('runtime omits host credentials and cannot connect outside its network namespace',async()=>{
  const run=createReadOnlyExecutor({cwd:process.cwd()});
  const r=await run({name:'bash',arguments:JSON.stringify({command:"/usr/bin/python3 - <<'PY'\nimport os,socket\nprint('DEEPSEEK_API_KEY' in os.environ)\ns=socket.socket();s.settimeout(.2)\ntry: s.connect(('1.1.1.1',443));print('connected')\nexcept OSError: print('network unavailable')\nPY"})});
  assert.equal(r.isError,false,r.text);assert.match(r.text,/False\nnetwork unavailable/);
});

test('unsupported writes and background jobs are rejected without spawning',async()=>{
  const run=createReadOnlyExecutor({cwd:process.cwd()});
  assert((await run({name:'write',arguments:'{}'})).isError);
  assert((await run({name:'bash',arguments:'{"command":"true","run_in_background":true}'})).isError);
});

test('an archived workspace is visible at the original absolute task path',async t=>{
  const cwd=await mkdtemp(join(tmpdir(),'dsh-review-mapped-'));t.after(()=>rm(cwd,{recursive:true,force:true}));
  await writeFile(join(cwd,'checkpoint.txt'),'historical state');
  const run=createReadOnlyExecutor({cwd,logicalCwd:'/work/original-task'});
  const r=await run({name:'bash',arguments:JSON.stringify({command:'cd /work/original-task && /usr/bin/python3 -c "print(open(\'checkpoint.txt\').read())"'})});
  assert.equal(r.isError,false,r.text);assert.match(r.text,/historical state/);
});
