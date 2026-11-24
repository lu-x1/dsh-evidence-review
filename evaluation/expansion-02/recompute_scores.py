"""Offline score/cost integrity checks, not independent replication/adjudication."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent


def load(name):
    return json.loads((HERE / name).read_text())


def main():
    # Retain and verify the original report, source and mechanism-test hashes.
    runpy.run_path(str(HERE.parent / 'recompute_scores.py'), run_name='__main__')
    report, rows, cases = load('results.json'), load('decisions.json'), load('cases.json')
    assert len({r['id'] for r in rows}) == len(rows) == 24
    assert len({r['id'] for r in cases}) == len(cases) == 10
    errors = [r for r in rows if r['label'] == 'error']
    normals = [r for r in rows if r['label'] == 'normal']
    previous = [r for r in errors if r['cohort'] == 'previous_development']
    new = [r for r in errors if r['cohort'] == 'new_Kiva']
    def count(values):
        return {'n': sum(r['target_detected'] is True for r in values), 'N': len(values)}
    assert report['previous_error_detection'] == count(previous)
    assert report['new_Kiva_error_detection'] == count(new)
    assert report['pooled_measured_error_detection'] == count(errors) | {'fraction': count(errors)['n'] / len(errors)}
    assert report['normal_false_reminder'] == {'n': sum(r['false_reminder'] for r in normals), 'N': len(normals)}
    assert report['normal_completed_on_track'] == {'n': sum(r['completed'] and r['decision'] in ('on-track', 'normal_completed_on_track') for r in normals), 'N': len(normals)}
    assert report['endpoint_review_completion'] == {'n': sum(r['completed'] for r in rows), 'N': len(rows)}
    kiva = [r for r in rows if r['cohort'] == 'new_Kiva']
    assert report['new_Kiva_review_completion'] == {'n': sum(r['completed'] for r in kiva), 'N': len(kiva)}
    assert report['new_Kiva_error_reviews_unfinished'] == {'n': sum(not r['completed'] for r in new), 'N': len(new)}
    by_id = {r['id']: r for r in rows}
    untested = {r['id'] for r in cases} - {r['id'] for r in errors}
    assert set(report['untested_error_checkpoints']) == untested == {'F26'}
    for case in cases:
        assert case['target_detected_current_batch'] == (by_id[case['id']]['target_detected'] if case['id'] in by_id else None)
    assert report['dataset']['error_checkpoints'] == len(cases)
    assert report['dataset']['normal_checkpoints'] == len(normals)
    assert report['dataset']['checkpoints'] == len(cases) + len(normals)
    inherited = json.loads((HERE.parent / 'review-decisions.json').read_text())['rows']
    for r in inherited:
        assert by_id[r['id']]['target_detected'] == r['usable_primary_reminder']
    source = load('source.json')
    assert source['completed_questions'] == len(source['scores']) == 20
    assert source['score_fraction'] == sum(r['score'] for r in source['scores']) / len(source['scores'])
    assert source['source_answer_score'] == '13/20'
    assert source['planned_questions'] == 37 and source['censored_during_question'] == 21
    assert source['full37_terminal_outcome'] is None
    periodic = load('periodic.json')
    assert periodic['original_C']['checks'] == [{'ordinal': 8, 'assessment': 'on-track', 'target_detected': False}]
    recovery = periodic['resource_recovery_C']
    assert recovery['restored_counter'] == 6 and recovery['first_request_equals_original_first_C16_request']
    assert not recovery['raw_share_formula_error_detected'] and not recovery['raw_share_formula_restored_in_completed16']
    assert recovery['notice_enqueued'] == recovery['notice_visible_in_next_local_request'] == 1
    assert recovery['notice_forwarded_to_provider'] == recovery['notice_consumed_by_model'] == 0
    prefix = periodic['jointly_completed_prefix']
    assert prefix['questions'] == [14, 15, 16] and prefix['N_scores'] == prefix['C_scores'] == [1, 1, 0]
    assert prefix['full_four_question_score_gain'] is None and prefix['question17_C_score'] is None
    assert report['overall_ten_case_repair_rate'] is None
    usage = load('usage.json')
    prices = {k: Decimal(v) / 1000000 for k, v in usage['usd_per_million'].items()}
    phase_totals = {}
    for r in usage['rows']:
        assert 0 <= r['cached_input_tokens'] <= r['input_tokens']
        predicted = (r['cached_input_tokens'] * prices['cached_input'] +
            (r['input_tokens'] - r['cached_input_tokens']) * prices['uncached_input'] +
            r['output_tokens_including_thinking'] * prices['output_including_thinking'])
        assert predicted == Decimal(r['fee_usd']), (r['phase'], r['turn'])
        phase_totals[r['phase']] = phase_totals.get(r['phase'], Decimal(0)) + predicted
    total = sum(phase_totals.values())
    assert total == Decimal(usage['incremental_fee_usd'])
    assert sum(r['calls'] for r in usage['rows']) == 221
    after = Decimal(usage['cumulative_exposure_before_usd']) + total
    assert after == Decimal(usage['cumulative_exposure_after_usd']) == Decimal(report['cumulative_budget_exposure_usd'])
    assert after <= Decimal(usage['cumulative_authorized_cap_usd']) == Decimal(12)
    assert Decimal(usage['remaining_usd']) == Decimal(12) - after
    assert Decimal(usage['remaining_usd']) < Decimal(usage['last_local_refusal']['required_reservation_usd'])
    assert phase_totals['periodic_C_original'] + phase_totals['periodic_C_recovery'] == Decimal(periodic['all_C_attempts_cost_usd'])
    manifest = load('export-sha256.json')
    for name, expected in manifest.items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == expected, name
    print(json.dumps({'status': 'passed', 'measured_error_detection': count(errors),
        'normal_false_reminder': report['normal_false_reminder'],
        'reviews_completed': report['endpoint_review_completion'], 'source_answer_score': source['source_answer_score'],
        'incremental_fee_usd': str(total), 'cumulative_exposure_usd': str(after),
        'phase_fees_usd': {k: str(v) for k, v in phase_totals.items()}, 'new_model_calls': 0}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
