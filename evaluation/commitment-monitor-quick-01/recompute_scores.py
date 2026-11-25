"""Free arithmetic check; published author judgments are not independent truth."""
from decimal import Decimal
import json
from pathlib import Path


def recompute():
    root=Path(__file__).resolve().parent
    m=json.loads((root/'metrics.json').read_text());t=m['totals'];rows=m['rows'];usage=m['request_usage']
    assert len(rows)==18 and len({r['id'] for r in rows})==18
    assert sum(r['upstream_calls']>0 for r in rows)==t['started_points']==17
    assert sum(r['effective_complete'] for r in rows)==t['effective_complete']==13
    assert sum(r['target_reminder'] for r in rows)==t['target_reminders']==3
    assert sum(r['kind']=='error' and r['upstream_calls']>0 for r in rows)==t['target_errors_started']==6
    assert sum(r['kind']=='normal' and r['upstream_calls']>0 for r in rows)==t['normal_points_started']==11
    assert sum(r['kind']=='normal' and r['effective_complete'] and r['assessment']=='on-track' for r in rows)==t['normal_complete_on_track']==9
    assert sum(r['false_reminder'] for r in rows)==t['normal_false_reminders']==0
    assert len(usage)==t['upstream_calls']==31 and len({u['opaque_request_sha256'] for u in usage})==31
    assert all(u['status']=='settled' and u['http_status']==200 and u['forward_attempted'] for u in usage)
    for r in rows:
        if r['target_reminder']:assert r['effective_complete'] and r['kind']=='error' and r['assessment']=='drift'
        assert sum((Decimal(u['fee_usd']) for u in usage if u['point']==r['id']),Decimal(0))==Decimal(r['settled_fee_usd'])
    for field in ('input_tokens','cached_input_tokens','output_tokens_including_thinking'):
        assert sum(u[field] for u in usage)==t[field]
    assert round(100*t['cached_input_tokens']/t['input_tokens'],4)==t['cache_hit_rate_percent']
    f=m['finances'];total=sum((Decimal(u['fee_usd']) for u in usage),Decimal(0))
    assert total==Decimal(f['new_settled_fee_usd'])==Decimal('0.275311104000')
    first=json.loads((root.parent/'commitment-monitor-01/metrics.json').read_text())
    assert Decimal(f['global_exposure_usd'])-Decimal(first['finances']['global_exposure_usd'])==total
    assert Decimal(f['cumulative_cap_usd'])-Decimal(f['global_exposure_usd'])==Decimal(f['remaining_capacity_usd'])
    c=json.loads((root/'coverage.json').read_text())
    assert len(c['rows'])==25 and c['S_points_with_confirmed_upstream_calls']==23
    assert c['S_complete']==first['arms']['S']['complete']+t['effective_complete']==19
    assert c['S_errors_target_reminders']==first['arms']['S']['target_reminders']+t['target_reminders']==5
    assert c['S_normal_complete_on_track']==first['arms']['S']['normal_complete_on_track']+t['normal_complete_on_track']==12
    assert sum(r['kind']=='normal' and r['S_upstream_calls']>0 for r in c['rows'])==14
    assert m['unstarted_ids']==['N-WD36'] and m['actor_continuations']==0 and m['correction_rate'] is None
    recovery=json.loads((root/'reply-compat-regression.json').read_text())
    assert recovery['recovered_normal_ids']==['N-L10'] and recovery['unchanged_original_valid_reviews']==19
    return {'status':'public_arithmetic_verified_not_independent_semantic_audit',
        'coverage_including_first6':'23/24 called,19/23 complete',
        'target_errors':'5/9 reminded,2 missed,2 unfinished','normals':'12/14 complete,0/14 false reminders',
        'posthoc_compat_normal_recovery':1,'new_fee_usd':str(total),'actual_correction_rate':'not_measured'}


if __name__=='__main__':print(json.dumps(recompute(),ensure_ascii=False,indent=2))
