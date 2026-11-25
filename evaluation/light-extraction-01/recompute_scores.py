"""No network/model calls; recompute delivery, timing, and cost only."""
import json
from pathlib import Path
from decimal import Decimal
import statistics

p = Path(__file__).parent
m = json.loads((p / 'metrics.json').read_text())
rows = m['rows']
assert len(rows) == m['model_calls'] and len({r['id'] for r in rows}) == len(rows)
assert all(r['drained'] for r in rows)
assert sum(Decimal(r['fee_usd']) for r in rows if r['fee_usd'] is not None) == Decimal(m['estimated_fee_usd'])
assert sum(Decimal(r['unsettled_hold_usd']) for r in rows) == Decimal(m['unsettled_new_hold_usd'])
assert len(rows) + len(m['not_forwarded']) == m['planned_model_requests']
for mode, summary in m['modes'].items():
    selected = [r for r in rows if r['mode'] == mode]
    assert len(selected) == summary['forwarded']
    assert sum(r['usable'] for r in selected) == summary['on_time_usable']
    assert sum(r['schema_valid'] for r in selected) == summary['schema_valid']
    completed = [r for r in selected if r['finish'] is not None]
    assert len(completed) == summary['model_completed']
    assert sum(Decimal(r['fee_usd']) for r in selected if r['fee_usd'] is not None) == Decimal(summary['fee_usd'])
    assert round(statistics.mean(r['wall_seconds'] for r in completed), 6) == summary['mean_completed_wall_seconds']
    for r in selected:
        assert r['usable'] == (r['schema_valid'] and not r['unknown_source_ids']
            and r['finish'] == 'stop' and r['wall_seconds'] < 60)
    assert sum(all(any(r['point'] == point and r['side'] == side and r['usable']
        for r in selected) for side in ('expected', 'actual'))
        for point in {r['point'] for r in rows}) == summary['fully_delivered_points']
assert m['detection_or_repair_score'] is None
assert all(r['model_detection_success'] is None and r['repair_success'] is None for r in rows)
print(json.dumps({'points':m['development_points'], 'calls':len(rows),
    'delivery':{k:v['on_time_usable'] for k,v in m['modes'].items()},
    'fee_usd':m['estimated_fee_usd'], 'new_hold_usd':m['unsettled_new_hold_usd'],
    'not_forwarded':len(m['not_forwarded']), 'detection_or_repair_score':None}, ensure_ascii=False))
