"""Free check of the published per-point judgments and sanitized usage."""
from decimal import Decimal
from pathlib import Path
import json


def recompute():
    root=Path(__file__).resolve().parent
    m=json.loads((root/'metrics.json').read_text())
    audit=json.loads((root/'semantic-audit.json').read_text())
    usage=json.loads((root/'request-usage.json').read_text())['rows']
    assert len(usage)==22 and len({r['opaque_request_sha256'] for r in usage})==22
    assert len(m['rows'])==len(audit['rows'])==12
    judgments={(r['id'],r['arm']):r for r in audit['rows']}
    for arm in ('R0','S'):
        rows=[r for r in m['rows'] if r['arm']==arm];expected=m['arms'][arm]
        receipts=[r for r in usage if r['arm']==arm]
        assert len(rows)==6 and len({r['id'] for r in rows})==6
        assert sum(r['status']=='complete' for r in rows)==expected['complete']==6
        assert sum(r['target_reminder'] for r in rows)==expected['target_reminders']==2
        assert sum(r['false_reminder'] for r in rows)==expected['normal_false_reminders']==0
        assert sum(r['kind']=='normal' and r['assessment']=='on-track' for r in rows)==expected['normal_complete_on_track']==3
        for r in rows:
            j=judgments[r['id'],arm]
            for k,v in j.items():assert r[k]==v
            if r['target_reminder']:assert r['kind']=='error' and r['assessment']=='drift'
            assert sum((Decimal(u['fee_usd']) for u in receipts if u['point']==r['id']),Decimal(0))==Decimal(r['fee_usd'])
        assert len(receipts)==expected['upstream_calls']
        assert all(r['status']=='settled' and r['http_status']==200 and r['forward_attempted'] for r in receipts)
        for field in ('input_tokens','cached_input_tokens','output_tokens_including_thinking'):
            assert sum(r[field] for r in receipts)==expected[field]
        hit=round(100*expected['cached_input_tokens']/expected['input_tokens'],4)
        assert hit==expected['cache_hit_rate_percent']
        assert sum((Decimal(r['fee_usd']) for r in receipts),Decimal(0))==Decimal(expected['fee_usd'])
        assert sum(r['tools'] for r in rows)==expected['tools']
    total=sum((Decimal(r['fee_usd']) for r in usage),Decimal(0))
    assert total==Decimal(m['new_settled_fee_usd'])==Decimal('0.205661100000')
    f=m['finances']
    assert Decimal(f['global_exposure_usd'])-Decimal(f['exposure_before_usd'])==total
    assert Decimal(f['cumulative_cap_usd'])-Decimal(f['global_exposure_usd'])==Decimal(f['remaining_capacity_usd'])
    assert m['actor_continuations']==0 and m['causal_correction_success_rate'] is None
    return {'status':'published_arithmetic_verified_not_independent_semantic_review','target_reminders':{'R0':'2/3','S':'2/3'},
        'normal_false_reminders':{'R0':'0/3','S':'0/3'},'settled_requests':len(usage),'fee_usd':str(total),
        'actual_correction_rate':'not_measured','all_seen_development':True}


if __name__=='__main__':print(json.dumps(recompute(),ensure_ascii=False,indent=2))
