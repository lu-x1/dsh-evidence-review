"""Recount published diagnostic rows, fees and prospective screen; zero API."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path


def main():
    root=Path(__file__).resolve().parent;d=json.loads((root/'metrics.json').read_bytes());result={}
    for name,digest in d['baseline_source_sha256'].items():assert hashlib.sha256((root.parents[1]/'src'/name).read_bytes()).hexdigest()==digest
    for name in ['atomic','compact','compact_low']:
        r=d[name];s=r['summary'];rows=r['rows'];assert len(rows)==len({v['id'] for v in rows})==s['planned']
        errors=[v for v in rows if v['kind']=='error'];normal=[v for v in rows if v['kind']=='normal']
        for v in rows:
            if v['target_reminder']:assert v['kind']=='error' and v['status']=='complete' and v['assessment']=='drift' and v['recognized_target_including_late']
            if v['false_reminder']:assert v['kind']=='normal' and v['status']=='complete' and v['assessment']=='drift'
        counts={'forwarded_points':sum(v['forwarded'] for v in rows),'errors':len(errors),'normal':len(normal),
            'target_reminders':sum(v['target_reminder'] is True for v in errors),
            'recognized_targets_including_late':sum(v['recognized_target_including_late'] is True for v in errors),
            'normal_false_reminders':sum(v['false_reminder'] for v in normal),
            'normal_complete_on_track':sum(v['status']=='complete' and v['assessment']=='on-track' for v in normal),
            'complete':sum(v['status']=='complete' for v in rows),'calls':sum(v['calls'] for v in rows),
            'reference_target_reminders':sum(v['reference_target_reminder'] is True for v in errors)}
        for k,v in counts.items():assert s[k]==v,(name,k)
        fee=sum((Decimal(v['fee_usd']) for v in rows),Decimal(0));assert fee==Decimal(s['fee_usd'])
        assert sum((Decimal(v['reference_fee_usd']) for v in rows),Decimal(0))==Decimal(s['reference_fee_usd'])
        result[name]={**counts,'fee_usd':str(fee)}
    for name in ['compact','compact_low']:
        r=d[name];s=r['summary']
        rules=d['prospective_screening_plan']['screen_for_next_stage_only'] if name=='compact' else d['prospective_low_plan']['screening_same_rules_as_compact_high']
        hard=set(d['prospective_screening_plan']['hard_target_subset']);found=sum(v['target_reminder'] is True for v in r['rows'] if v['id'] in hard)
        assert found==s['hard_target_reminders'] and len(hard)==s['hard_target_denominator']
        checks={'all_registered_draws_forwarded_and_closed':s['forwarded_points']==8 and r['raw_status']=='complete_pending_target_adjudication',
            'hard_targets':found>=rules['hard_targets_with_valid_ontime_reminder_at_least'],
            'false_reminders':s['normal_false_reminders']<=rules['normal_false_reminders_at_most'],
            'normal_completion':s['normal_complete_on_track']>=rules['normal_completed_on_track_at_least'],
            'review_completion':s['complete']>=rules['all_reviews_complete_at_least'],
            'fees':Decimal(s['fee_usd'])<=Decimal(rules['estimated_phase_fee_usd_at_most'])}
        assert checks==r['screening']['checks'] and all(checks.values())==r['screening']['passed']
    print(json.dumps({'status':'scores_fees_screen_and_default_source_match','probes':result,
        'compact_high_screening':d['compact']['screening'],'compact_low_screening':d['compact_low']['screening'],
        'manual_labels_not_independent_rerating':True,'model_calls':0},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
