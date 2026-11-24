"""Recount development-probe records and receipt totals; no API or raw task data."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path


def main():
    root=Path(__file__).resolve().parent
    d=json.loads((root/'metrics.json').read_bytes())
    for name,digest in d['baseline_source_sha256'].items():
        assert hashlib.sha256((root.parents[1]/'src'/name).read_bytes()).hexdigest()==digest
    result={}
    for name in ['low_review','code_index']:
        r=d[name];rows=r['rows'];s=r['summary']
        assert len(rows)==len({v['id'] for v in rows})==s['planned']
        errors=[v for v in rows if v['kind']=='error'];normal=[v for v in rows if v['kind']=='normal']
        assert len(errors)==s['errors'] and len(normal)==s['normal']
        for v in rows:
            if v['target_reminder']:
                assert v['kind']=='error' and v['status']=='complete' and v['assessment']=='drift' and v['recognized_target_including_late']
            if v['false_reminder']:assert v['kind']=='normal' and v['status']=='complete' and v['assessment']=='drift'
        counts={'target_reminders':sum(v['target_reminder'] is True for v in errors),
            'normal_false_reminders':sum(v['false_reminder'] for v in normal),
            'normal_complete_on_track':sum(v['status']=='complete' and v['assessment']=='on-track' for v in normal),
            'complete':sum(v['status']=='complete' for v in rows),'calls':sum(v['calls'] for v in rows),
            'prior_high_target_reminders':sum(v['prior_high_target_reminder'] is True for v in errors)}
        for key,value in counts.items():assert s[key]==value,(name,key)
        fee=sum((Decimal(v['fee_usd']) for v in rows),Decimal(0));assert fee==Decimal(s['fee_usd'])
        high_fee=sum((Decimal(v['prior_high_fee_usd']) for v in rows),Decimal(0));assert high_fee==Decimal(s['prior_high_fee_usd'])
        result[name]={**counts,'errors':len(errors),'normal':len(normal),'fee_usd':str(fee)}
    cache=d['cache_probe'];assert len(cache['groups'])==2
    total=Decimal(0);calls=0
    for group in cache['groups']:
        assert len(group['rows'])==4
        for v in group['rows']:assert v['cache_hit_percent']==round(100*v['cached_tokens']/v['input_tokens'],4)
        fee=sum((Decimal(v['fee_usd']) for v in group['rows']),Decimal(0));assert fee==Decimal(group['fee_usd'])
        total+=fee;calls+=4
    assert total==Decimal(cache['fee_usd']) and calls==cache['calls']==8
    print(json.dumps({'status':'scores_fees_and_default_source_match','probes':result,
        'synthetic_cache_calls':calls,'synthetic_cache_fee_usd':str(total),
        'manual_labels_not_independent_rerating':True,'model_calls':0},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
