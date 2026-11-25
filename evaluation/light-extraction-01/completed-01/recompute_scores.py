import json
from decimal import Decimal
from pathlib import Path
import statistics

m=json.loads((Path(__file__).parent/'metrics.json').read_text())
rows=m['rows'];attempts=m['attempts']
assert len(rows)==m['logical_inputs']==m['model_completions']==24
assert len({r['id'] for r in rows})==24 and len(attempts)==m['upstream_attempts']==25
assert len({(r['attempt_group'],r['id']) for r in attempts})==25
assert sum(r['http_status']==402 for r in attempts)==1
assert all(r['drained'] for r in attempts)
assert sum(Decimal(r['fee_usd']) for r in attempts if r['fee_usd'] is not None)==Decimal(m['estimated_fee_usd'])
assert sum(Decimal(r['unsettled_hold_usd']) for r in attempts)==Decimal(m['unsettled_new_hold_usd'])
assert all(r['settled'] for r in rows)
for mode,s in m['modes'].items():
    selected=[r for r in rows if r['mode']==mode]
    assert len(selected)==s['planned_inputs']==s['model_completed']==12
    assert sum(r['usable'] for r in selected)==s['on_time_usable']
    assert sum(r['schema_valid'] for r in selected)==s['schema_valid']
    assert round(statistics.mean(r['wall_seconds'] for r in selected),6)==s['mean_completed_wall_seconds']
    assert sum(Decimal(r['fee_usd']) for r in selected)==Decimal(s['fee_usd'])
    assert sum(all(any(r['point']==p and r['side']==side and r['usable'] for r in selected)
        for side in ('expected','actual')) for p in {r['point'] for r in rows})==s['fully_delivered_points']
    for r in selected:
        assert r['usable']==(r['schema_valid'] and not r['unknown_source_ids'] and r['wall_seconds']<60 and r['finish']=='stop')
assert m['detection_or_repair_score'] is None
assert all(r['model_detection_success'] is None and r['repair_success'] is None for r in attempts)
print(json.dumps({'points':6,'logical_inputs':24,'upstream_attempts':25,
    'delivery':{k:v['on_time_usable'] for k,v in m['modes'].items()},
    'settled_fee_usd':m['estimated_fee_usd'],'unsettled_hold_usd':m['unsettled_new_hold_usd'],
    'detection_or_repair_score':None},ensure_ascii=False))
