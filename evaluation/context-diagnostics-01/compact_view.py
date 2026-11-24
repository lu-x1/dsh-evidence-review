"""Research-only Chat Completions view; not a native DSH adapter integration."""
from copy import deepcopy
import json

def compose(body):
    text=body['messages'][-1]['content'];instruction,payload=text.split('\n\n',1)
    data=json.loads(payload);original=deepcopy(data)
    data['execution_code_index']['provenance']='Exact excerpts from archived public assistant tool-call Python source. This diagnostic omits the full actor trajectory; the selected excerpts are the available code view. Observed code is not user authorization, proof of successful execution, or proof of current applicability. Check the original artifact and scope before judging.'
    data['context_view']={'kind':'original_system_plus_full_user_requirements_candidate_and_partial_code_index',
        'omitted':'Original assistant/tool trajectory, including unselected implementation details and observations.',
        'coverage_limit':'Missing history is not proof of correctness or drift. Use the existing bounded read-only tools for a material uncertainty, or return unknown if it cannot be established.'}
    restored=deepcopy(data);restored.pop('context_view');restored['execution_code_index']['provenance']=original['execution_code_index']['provenance']
    assert restored==original
    # Inspect role tags only. Never read or summarize private assistant reasoning.
    system=[v for v in body['messages'][:-1] if v.get('role')=='system']
    assert system
    result={**body,'messages':[*system,{'role':'user','content':instruction+'\n\n'+json.dumps(data,ensure_ascii=False,separators=(',',':'))}]}
    assert {k:v for k,v in result.items() if k!='messages'}=={k:v for k,v in body.items() if k!='messages'}
    return result
