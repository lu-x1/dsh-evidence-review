"""Public score/fee recount from manual records; zero external dependencies/API."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path


def main():
    here=Path(__file__).resolve().parent
    data=json.loads((here/'metrics.json').read_text())
    rows=data['rows'];stored=data['summary']
    assert len(rows)==48 and len({(v['id'],v['arm']) for v in rows})==48
    for name,digest in data['baseline_source_sha256'].items():
        assert hashlib.sha256((here.parents[1]/'src'/name).read_bytes()).hexdigest()==digest,'default baseline source differs from study'
    result={}
    for arm in ['R0','R1']:
        selected=[v for v in rows if v['arm']==arm]
        errors=[v for v in selected if v['kind']=='error'];normal=[v for v in selected if v['kind']=='normal']
        assert len(errors)==9 and len(normal)==15
        for v in selected:
            if v['target_reminder']:
                assert v['kind']=='error' and v['controller_status']=='complete' and v['assessment']=='drift' and v['recognized_target_including_late']
        score={'target_reminders':sum(v['target_reminder'] is True for v in errors),
            'target_reminders_excluding_quality_caveat':sum(v['target_reminder'] is True and not v['quality_caveat'] for v in errors),
            'recognized_targets_including_late':sum(v['recognized_target_including_late'] is True for v in errors),
            'normal_false_reminders':sum(v['false_reminder'] for v in normal),
            'normal_complete_on_track':sum(v['controller_status']=='complete' and v['assessment']=='on-track' for v in normal),
            'complete':sum(v['controller_status']=='complete' for v in selected),
            'review_calls':sum(v['review_calls'] for v in selected)}
        for key,value in score.items():assert stored['arms'][arm][key]==value,(arm,key)
        review=sum((Decimal(v['review_fee_usd']) for v in selected),Decimal(0))
        cards=sum((Decimal(v['card_fee_usd']) for v in selected),Decimal(0))
        assert review==Decimal(stored['arms'][arm]['review_fee_usd'])
        if arm=='R1':
            assert cards==Decimal(stored['R1_extraction_fee_including_reused_pilot_usd'])
            assert review+cards==Decimal(stored['R1_method_fee_usd'])
        else:assert cards==0
        result[arm]={**score,'review_fee_usd':str(review),'extraction_fee_usd':str(cards),'method_fee_usd':str(review+cards)}
    assert sum(v['card_status']=='ready' for v in rows if v['arm']=='R1')==stored['cards_ready']
    print(json.dumps({'status':'counts_fees_and_baseline_source_match','cases':24,'errors':9,'normal':15,'arms':result,
        'manual_nonblind_labels_not_independent_rerating':True,'model_calls':0},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
