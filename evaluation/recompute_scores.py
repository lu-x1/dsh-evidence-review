"""Recompute the public report from exported decisions; standard library, no API calls.

This verifies score arithmetic and source identity, not the correctness of the
original nonblind adjudication or independent reproducibility of private runs.
"""
import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT / name).read_text())


def main():
    cases = load('cases.json')
    case_ids = {r['id'] for r in cases}
    assert case_ids == {'W25', 'F10', 'F16', 'F24', 'F26', 'L18', 'NFL3'}
    decisions = load('review-decisions.json')['rows']
    assert len(decisions) == len({r['id'] for r in decisions}) == 14
    positives = [r for r in decisions if r['id'] in case_ids]
    normals = [r for r in decisions if r['id'] not in case_ids]
    assert {r['id'] for r in positives} == case_ids - {'F26'}
    assert {r['id'] for r in positives if r['usable_primary_reminder']} == {'F10', 'F16', 'F24'}
    assert all(r['decision'] == 'normal_completed_on_track' for r in normals)
    complete_decisions = {
        'correct_primary_scope_conflict', 'normal_completed_on_track',
        'primary_missed_normal_verdict', 'primary_missed_other_description_error_reported',
    }
    assert all(r['decision'] in complete_decisions for r in decisions)
    expected = {
        'target_detected': sum(r['usable_primary_reminder'] for r in positives),
        'target_error_denominator': len(positives),
        'target_detection_rate': sum(r['usable_primary_reminder'] for r in positives) / len(positives),
        'normal_false_reminders': sum(r['false_warning'] for r in normals),
        'normal_denominator': len(normals),
        'normal_false_reminder_rate': sum(r['false_warning'] for r in normals) / len(normals),
        'completed_reviews': len(decisions), 'attempted_reviews': len(decisions),
    }
    report = load('results.json')
    assert report['primary_diagnosis'] == expected
    by_id = {r['id']: r for r in decisions}
    for row in cases:
        actual = by_id[row['id']]['usable_primary_reminder'] if row['id'] in by_id else None
        assert row['target_detected_current_batch'] == actual
    assert report['overall_seven_case_repair_rate'] is None
    assert {r['id'] for r in cases if r['current_repair_result'] == 'not_run'} == {'W25', 'F16', 'L18', 'NFL3'}
    supplemental = load('supplemental-normal-decisions.json')['rows']
    assert len(supplemental) == 6
    assert report['supplemental_normals']['normal_denominator'] == len(supplemental)
    assert report['supplemental_normals']['completed_reviews'] == sum(r['completed'] for r in supplemental)
    assert report['supplemental_normals']['normal_false_reminders'] == sum(r['false_reminder'] for r in supplemental)
    assert all(r['assessment'] == 'on-track' for r in supplemental)
    repair = load('repair-results.json')
    condition = repair['F10']
    assert condition['original_task10_answer_repair']['C'] is True
    assert condition['original_task10_answer_repair']['N'] is False
    assert condition['next_two_questions_correct'] == {'N': '2/2', 'C': '2/2'}
    pair = repair['F24_F26']
    terminal = report['native_periodic_terminal']
    assert pair['terminal_numeric_score'] == {'C': 0, 'N': 0}
    assert terminal['correct_with_plugin'] == pair['terminal_numeric_score']['C']
    assert terminal['correct_without_plugin'] == pair['terminal_numeric_score']['N']
    assert terminal['paired_task_denominator'] == pair['terminal_numeric_score_denominator_per_arm'] == 1
    c_fee = Decimal(str(pair['costs']['C']['total_fee_usd']))
    n_fee = Decimal(str(pair['costs']['N']['total_fee_usd']))
    assert Decimal(str(terminal['cost_with_plugin_usd'])) == c_fee
    assert Decimal(str(terminal['cost_without_plugin_usd'])) == n_fee
    cost_change = float(c_fee / n_fee - 1)
    assert math.isclose(cost_change, terminal['observed_cost_change_fraction'], abs_tol=1e-12)
    assert pair['scope_repaired_turn24'] is True and pair['turn25_adopted_pool'] == 32
    identity = load('source-identity.json')
    for name, digest in identity['sha256'].items():
        assert hashlib.sha256((ROOT.parent / name).read_bytes()).hexdigest() == digest, name
    metadata = json.loads((ROOT.parent / 'package.json').read_text())
    assert metadata['version'] == report['release_version'] == identity['package_version']
    assert report['runtime_source_commit'] == identity['runtime_source_commit']
    print(json.dumps({
        'status': 'passed', 'target_detection': f"{expected['target_detected']}/{len(positives)}",
        'target_detection_percent': 100 * expected['target_detection_rate'],
        'normal_false_reminders': f"{expected['normal_false_reminders']}/{len(normals)}",
        'supplemental_normal_false_reminders': '0/6',
        'native_periodic_terminal': 'with plugin 0/1; without plugin 0/1',
        'native_periodic_cost_change_percent': 100 * cost_change,
        'source_and_test_files_verified': len(identity['sha256']), 'model_calls': 0,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
