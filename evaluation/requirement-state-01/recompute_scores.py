"""Recompute public proposal-delivery metrics only; no API or task data."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path


def main():
    folder = Path(__file__).parent
    for name, digest in json.loads((folder / 'artifact-sha256.json').read_bytes()).items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest
    metrics = json.loads((folder / 'metrics.json').read_bytes())
    rows, summary = metrics['rows'], metrics['summary']
    prices = json.loads((folder / 'protocol.json').read_bytes())['prices_usd_per_million']
    assert len(rows) == summary['planned_requests'] == 12
    assert len({v['point'] for v in rows}) == summary['planned_points'] == 6
    assert len({v['id'] for v in rows}) == 12
    for point in {v['point'] for v in rows}:
        assert {v['arm'] for v in rows if v['point'] == point} == {'expected', 'actual'}
    assert sum(v['on_time_json_object'] for v in rows) == summary['on_time_json_objects']
    assert sum(v['finish'] == 'length' for v in rows) == summary['length_finishes']
    assert sum(v['public_chars'] == 0 for v in rows) == summary['empty_public_replies']
    assert sum(v['json_object_in_public_text'] for v in rows) == summary['any_json_objects_in_public_output']
    assert sum(Decimal(v['estimated_fee_usd']) for v in rows) == Decimal(summary['estimated_fee_usd'])
    for row in rows:
        calculated = ((row['input_tokens'] - row['cached_input_tokens']) * Decimal(prices['uncached_input'])
            + row['cached_input_tokens'] * Decimal(prices['cached_input'])
            + row['output_tokens'] * Decimal(prices['output'])) / Decimal(1000000)
        assert calculated == Decimal(row['estimated_fee_usd'])
    assert sum(v['output_tokens'] for v in rows) == summary['output_tokens']
    assert sum(v['input_tokens'] for v in rows) == summary['input_tokens']
    assert sum(v['cached_input_tokens'] for v in rows) == summary['cached_input_tokens']
    assert all(v['transport_settled'] and v['collector_drained'] and v['journal_archived'] for v in rows)
    assert all(not v['on_time_json_object'] or (v['json_object_in_public_text'] and v['wall_seconds'] < 60) for v in rows)
    assert summary['on_time_json_objects'] < summary['required_on_time_json_objects'] == 10
    assert summary['expanded_stage2_requests'] == 0
    assert summary['new_model_detection_score'] is None and summary['new_repair_score'] is None
    assert metrics['status'] == 'closed_failed_predeclared_delivery_gate'
    print(json.dumps({'status': 'verified', 'on_time_json': str(summary['on_time_json_objects']) + '/12',
        'empty_public_replies': summary['empty_public_replies'], 'estimated_fee_usd': summary['estimated_fee_usd'],
        'expanded_stage2_requests': 0, 'new_detection_or_repair_score': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
