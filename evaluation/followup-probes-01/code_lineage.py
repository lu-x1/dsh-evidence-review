"""Read-only index of public Python tool code; never executes source code."""
import ast
import hashlib
import json
import re
import shlex


def text_hash(value):return hashlib.sha256(value.encode()).hexdigest()


def python_sources(arguments):
    if isinstance(arguments,str):
        try:arguments=json.loads(arguments)
        except (TypeError,ValueError):return []
    if not isinstance(arguments,dict):return []
    result=[]
    for key in ['code','script']:
        if isinstance(arguments.get(key),str):result.append(arguments[key])
    if str(arguments.get('path',arguments.get('file_path',''))).endswith('.py') and isinstance(arguments.get('content'),str):
        result.append(arguments['content'])
    command=arguments.get('command')
    if isinstance(command,str):
        # Shell here-docs are inspected as text. No subprocess, eval or shell.
        for match in re.finditer(r"<<-?\s*['\"]?([A-Za-z_]\w*)['\"]?[^\n]*\n([\s\S]*?)^\1\s*$",command,re.M):
            header=command[:match.start()].split('\n')[-1]
            if re.search(r'python[\w.\-]*\s|[\w./-]+\.py\s*$',header):result.append(match.group(2))
        try:parts=shlex.split(command)
        except ValueError:parts=[]
        for i,item in enumerate(parts[:-1]):
            if item=='-c' and i and re.search(r'(?:^|/)python[\d.]*$',parts[i-1]):result.append(parts[i+1])
    return list(dict.fromkeys(result))


def public_calls(messages):
    for pos,message in enumerate(messages):
        if message.get('role')!='assistant':continue
        for call in message.get('tool_calls',[]):
            f=call.get('function',{})
            yield pos,call.get('id'),f.get('name'),f.get('arguments')
        content=message.get('content')
        if isinstance(content,list):
            for block in content:
                if block.get('type')=='tool-call':yield pos,block.get('id'),block.get('name'),block.get('arguments')


def fields(node):
    out=set()
    for n in ast.walk(node):
        if isinstance(n,ast.Subscript) and isinstance(n.slice,ast.Constant) and isinstance(n.slice.value,str):out.add(n.slice.value)
        elif isinstance(n,ast.Attribute):out.add(n.attr)
        elif isinstance(n,ast.Name):out.add(n.id)
    return out


def targets(node):
    if isinstance(node,ast.Subscript) and isinstance(node.slice,ast.Constant) and isinstance(node.slice.value,str):return [node.slice.value]
    if isinstance(node,ast.Attribute):return [node.attr]
    if isinstance(node,ast.Name):return [node.id]
    if isinstance(node,(ast.Tuple,ast.List)):return [v for n in node.elts for v in targets(n)]
    return []


def build_index(messages):
    records=[];parsed=0;failed=0;calls=0
    for pos,call_id,name,arguments in public_calls(messages):
        calls+=1
        for source in python_sources(arguments):
            try:tree=ast.parse(source)
            except SyntaxError:failed+=1;continue
            parsed+=1;source_id=f'm{pos}:{text_hash(source)[:12]}'
            helpers=[ast.get_source_segment(source,n) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
            io=[ast.get_source_segment(source,n) for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
                and n.func.attr in ['read_csv','read_pickle','to_csv','to_pickle','read_parquet','to_parquet']]
            for node in ast.walk(tree):
                value=None;names=[]
                if isinstance(node,ast.Assign):names=[v for n in node.targets for v in targets(n)];value=node.value
                elif isinstance(node,(ast.AnnAssign,ast.AugAssign)):names=targets(node.target);value=node.value
                if not names or value is None:continue
                code=ast.get_source_segment(source,node)
                for target in names:
                    records.append({'field':target,'source_id':source_id,'message_position':pos,'call_id':call_id,'tool_name':name,
                        'line':node.lineno,'code':code,'dependencies':sorted(fields(value)-{target}),
                        'target_kind':'column' if any(isinstance(t,(ast.Subscript,ast.Attribute)) for t in (node.targets if isinstance(node,ast.Assign) else [node.target])) else 'variable',
                        'expression_kind':'calculation' if any(isinstance(n,(ast.BinOp,ast.UnaryOp,ast.Compare,ast.BoolOp)) for n in ast.walk(value)) else 'numeric_constant' if isinstance(value,ast.Constant) and isinstance(value.value,(int,float)) else 'projection_or_call',
                        'helpers':[v for v in helpers if v and len(v)<=4000],'artifact_operations':io,
                        'status':'public_tool_proposal_only_not_proof_of_success_or_current_applicability'})
    return {'records':records,'public_calls_seen':calls,'python_blocks_parsed':parsed,'python_blocks_unparsed':failed}


def present(field,text):
    words=re.split(r'[_\s-]+',field)
    if len(field)<2:return False
    return bool(re.search(r'(?<!\w)'+r'[\s_-]*'.join(map(re.escape,words))+r'(?!\w)',text,re.I))


def cue(messages,candidate,latest_user,max_chars=18000):
    index=build_index(messages);records=index['records'];by_field={}
    focus=candidate
    try:
        response=json.loads(candidate)
        if isinstance(response,dict) and isinstance(response.get('answer'),str):
            focus=response['answer']+' '+str(response.get('reasoning_summary',''))
    except (TypeError,ValueError):pass
    for row in records:
        if row['field'] in ['answer','reasoning_summary','files_used','out']:continue
        if len(row['code'])>2500:continue
        by_field.setdefault(row['field'],[]).append(row)
    def score(field):
        rows=by_field[field]
        direct=2*present(field,latest_user)+present(field,focus)
        dep=max((sum(present(d,focus) for d in r['dependencies'] if len(d)>3) for r in rows),default=0)
        structural=any(r['target_kind']=='column' for r in rows) or any(r['expression_kind']=='calculation' for r in rows)
        return (bool(direct or dep),structural,min(4,direct+dep),rows[-1]['message_position'])
    seeds=[f for f in sorted(by_field,key=score,reverse=True) if score(f)[0] and score(f)[1]][:8]
    chosen=[];seen=set();queue=[(f,0) for f in seeds]
    while queue:
        field,depth=queue.pop(0)
        if field in seen or depth>3:continue
        seen.add(field);versions=[];code_seen=set()
        for row in reversed(by_field.get(field,[])):
            if row['code'] not in code_seen:versions.append(row);code_seen.add(row['code'])
            if len(versions)==2:break
        # Transporting a saved column must not hide its earlier arithmetic.
        arithmetic=next((r for r in reversed(by_field.get(field,[])) if r['expression_kind']=='calculation'),None)
        if arithmetic and arithmetic not in versions:versions.append(arithmetic)
        chosen+=versions
        for row in versions:
            queue.extend((d,depth+1) for d in row['dependencies'] if d in by_field and
                (any(v['target_kind']=='column' for v in by_field[d]) or any(v['expression_kind'] in ['calculation','numeric_constant'] for v in by_field[d])))
    recent=list(dict.fromkeys(r['source_id'] for r in reversed(records) if r['target_kind']=='column' and r['expression_kind']=='calculation'))[:2]
    for row in records:
        if row['source_id'] in recent and row['target_kind']=='column' and row['field'] not in ['answer','reasoning_summary','files_used'] and row not in chosen:chosen.append(row)
    output=[];contexts={};used=0
    for row in chosen:
        brief={k:v for k,v in row.items() if k not in ['helpers','artifact_operations','message_position','call_id','tool_name','status','target_kind','expression_kind']}
        relevant=[h for h in row['helpers'] if any(re.match(r'(?:async\s+)?def\s+'+re.escape(d)+r'\b',h) for d in row['dependencies'])]
        old_context=contexts.get(row['source_id'])
        context={'source_id':row['source_id'],'message_position':row['message_position'],'call_id':row['call_id'],'tool_name':row['tool_name'],'status':row['status'],'helpers':list(dict.fromkeys((old_context or {}).get('helpers',[])+relevant)),
            'artifact_operations':row['artifact_operations'][:6],'artifact_operations_omitted':max(0,len(row['artifact_operations'])-6)}
        size=len(json.dumps(brief,ensure_ascii=False))+len(json.dumps(context,ensure_ascii=False))-(len(json.dumps(old_context,ensure_ascii=False)) if old_context else 0)
        if used+size>max_chars:continue
        output.append(brief);contexts[row['source_id']]=context;used+=size
    return {'provenance':'Exact excerpts indexed from public assistant tool-call Python source already present in the original prefix. Observed code is not user authorization, proof of successful execution, or proof of current applicability. Check the original call, result, artifact and scope before judging.',
        'coverage':'Partial deterministic Python AST index. Unsupported syntax/languages and omitted entries are not verified correct.',
        'selection':'Candidate/latest-user field or dependency name matches; prefer column/calculation definitions; dependency closure up to3; at most2 recent distinct versions plus one older arithmetic version per field, and recent calculated columns. Excludes output-schema prose assignments; helper/artifact context is partial.',
        'seed_fields':seeds,'entries':output,'source_contexts':list(contexts.values()),'entries_omitted':len(chosen)-len(output),
        'public_calls_seen':index['public_calls_seen'],'python_blocks_parsed':index['python_blocks_parsed'],'python_blocks_unparsed':index['python_blocks_unparsed']}
