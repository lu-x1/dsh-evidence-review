import { spawn } from 'node:child_process';
import { existsSync, realpathSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve, sep } from 'node:path';

const READ_SCRIPT=String.raw`
import glob,json,pathlib,re,sys
op,a=json.loads(sys.argv[1])
p=pathlib.Path(a.get('file_path',a.get('path','.')))
if op=='read':
 if p.stat().st_size>2000000: raise ValueError('file too large for a small review read; use a targeted calculation')
 lines=p.read_text().splitlines();start=max(0,int(a.get('offset',1))-1);limit=min(300,max(1,int(a.get('limit',100))))
 for i,line in enumerate(lines[start:start+limit],start+1): print(str(i)+': '+line)
 if start+limit<len(lines): print('[more lines omitted]')
elif op=='glob':
 for f in sorted(glob.glob(str(p/a.get('pattern','*')),recursive=True))[:100]: print(f)
elif op=='grep':
 rx=re.compile(a['pattern']);count=0
 files=[p] if p.is_file() else sorted(p.rglob(a.get('glob','*')))
 for f in files:
  if not f.is_file() or f.stat().st_size>2000000: continue
  try: lines=f.read_text().splitlines()
  except (UnicodeError,OSError): continue
  for i,line in enumerate(lines,1):
   if rx.search(line):
    print(str(f)+':'+str(i)+': '+line);count+=1
    if count>=100: sys.exit(0)
`;

function inside(path,root) {
  const r=relative(root,path);return r===''||(!r.startsWith('..'+sep)&&r!=='..'&&!isAbsolute(r));
}

// This is an independent read-only execution channel, never ctx.tools.execute
// on the actor. The actor is paused while this channel is in use. No directory
// copies or model-provider credentials are needed by the tool subprocess.
export function createReadOnlyExecutor({cwd,logicalCwd=cwd,pythonExecutable='/usr/bin/python3',toolTimeoutMs=15000,maxOutputBytes=16000}={}) {
  return async function executeTool(call,signal) {
    let args;
    try {args=JSON.parse(call.arguments);} catch {return failure('Invalid tool arguments. Give a verdict from available evidence or request a valid small verification.');}
    if(!['bash','read','glob','grep'].includes(call.name)) return failure('This review channel supports only bash, read, glob and grep. Continue verification with these tools or return unknown.');
    if(!cwd||!isAbsolute(cwd)||!existsSync(cwd))return failure('No usable review working directory; use existing history or return unknown.');
    if(args.run_in_background||args.sandbox_permissions) return failure('Review tools run in the foreground without permission escalation.');
    if(!isAbsolute(logicalCwd))return failure('A review working directory must be absolute.');
    const workdir=resolve(logicalCwd,args.workdir??'.');
    if(!inside(workdir,logicalCwd))return failure('Review workdir must stay inside the task working directory.');
    if(!isAbsolute(pythonExecutable)||!existsSync(pythonExecutable))return failure('Configured Python runtime is unavailable.');
    const inner=call.name==='bash'
      ? ['/bin/bash','--noprofile','--norc','-c',args.command]
      : [pythonExecutable,'-c',READ_SCRIPT,JSON.stringify([call.name,args])];
    if(inner.some(x=>typeof x!=='string')||(call.name==='bash'&&!args.command.trim()))return failure('A nonempty command is required.');
    const mounts=['/usr','/bin','/lib','/lib64','/etc/ld.so.cache','/etc/alternatives',
      dirname(dirname(pythonExecutable)),dirname(dirname(realpathSync(pythonExecutable)))];
    const unique=[...new Set(mounts)].filter(p=>existsSync(p));
    // Never mount the host root or the surrounding home/workspace trees.
    const argv=['--die-with-parent','--new-session','--unshare-net','--unshare-pid','--unshare-ipc','--unshare-uts',
      '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/tmp/review-home'];
    for(const p of unique) {
      // A Python binary directly under /bin must not turn into a root mount.
      if(p==='/'||p==='/home')continue;
      argv.push('--ro-bind',p,p);
    }
    argv.push('--ro-bind',cwd,logicalCwd,'--chdir',workdir,'--clearenv',
      '--setenv','PATH','/usr/bin:/bin','--setenv','HOME','/tmp/review-home',
      '--setenv','TMPDIR','/tmp','--setenv','PYTHONDONTWRITEBYTECODE','1',
      '--setenv','LANG','C.UTF-8',...inner);
    const control=AbortSignal.any([...(signal?[signal]:[]),AbortSignal.timeout(toolTimeoutMs)]);
    return await new Promise(resolveResult=>{
      const child=spawn('bwrap',argv,{stdio:['ignore','pipe','pipe'],signal:control,env:{PATH:'/usr/bin:/bin'}});
      let bytes=0,text='',truncated=false,spawnError;
      const collect=chunk=>{
        const remaining=Math.max(0,maxOutputBytes-bytes);bytes+=chunk.length;
        if(remaining)text+=chunk.subarray(0,remaining).toString('utf8');
        if(bytes>maxOutputBytes) {truncated=true;child.kill('SIGKILL');}
      };
      child.stdout.on('data',collect);child.stderr.on('data',collect);
      child.on('error',error=>{spawnError=error.name;});
      child.on('close',(code,termination)=>resolveResult({isError:code!==0||Boolean(spawnError),
        text:text+(truncated?'\n[review tool output limit reached]':'')+
          `\n[exit code: ${code??'none'}${termination?'; signal: '+termination:''}${spawnError?'; '+spawnError:''}]`}));
    });
  };
}

function failure(text){return {isError:true,text};}
