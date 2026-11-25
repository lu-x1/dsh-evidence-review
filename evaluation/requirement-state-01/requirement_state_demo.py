"""Reproducible toy walkthrough; no benchmark labels, models or credentials."""
import json

from requirement_state import RequirementState, Source, reminder


def demo():
    sources = (
        Source('u0', 'user', '请在完整客户群上拟合四个分组，后续沿用这些标签。'),
        Source('u1', 'user', '现在只展示符合资格的客户，其他定义保持不变。'),
        Source('u2', 'user', '改为在符合资格的客户中重新拟合分组。'),
        Source('u3', 'user', '再调整一下分组方式。'),
        Source('a0', 'assistant', '保留完整客户群上拟合的标签，仅筛选展示符合资格的客户。'),
        Source('a1', 'assistant', '在符合资格的子集上重新拟合分组。'),
    )
    state = RequirementState(sources)

    def citation(sid):
        return {'source_id': sid, 'quote': next(v.text for v in sources if v.id == sid)}

    def apply(eid, kind, sid, **values):
        state.apply({'id': eid, 'kind': kind, 'citation': citation(sid),
                     'semantic_status': 'confirmed', **values})

    def record(name, population, sid, scope='eligible'):
        check = state.check('grouping', scope, {'fit_population': population}, citation(sid),
                            semantic_status='confirmed', stage='proposed')
        return {'step': name, 'result': check.status,
                'reason': [v.reason for v in check.findings], 'reminder': reminder([check])}

    apply('full', 'population', 'u0', population='full', parent=None)
    apply('grouping', 'add', 'u0', rule_id='grouping', scope='full', spec={'fit_population': 'full'})
    rows = [record('最初在完整客户群拟合', 'full', 'a0', 'full')]
    apply('begin-filter', 'begin_update', 'u1')
    apply('eligible', 'population', 'u1', population='eligible', parent='full')
    apply('end-filter', 'end_update', 'u1', resolved_sources=['u1'])
    rows.append(record('筛选展示，沿用原标签', 'full', 'a0'))
    rows.append(record('没有授权，却对子集重拟合', 'eligible', 'a1'))
    apply('begin-refit', 'begin_update', 'u2')
    apply('authorized-refit', 'replace', 'u2', rule_id='grouping', scope='full',
          expected_version=1, spec={'fit_population': 'eligible'})
    apply('end-refit', 'end_update', 'u2', resolved_sources=['u2'])
    rows.append(record('用户明确要求后，允许对子集重拟合', 'eligible', 'a1'))
    apply('begin-ambiguous', 'begin_update', 'u3')
    rows.append(record('新要求含糊且尚未解析，不沿用旧要求判正常', 'eligible', 'a1'))
    restored = RequirementState.replay(sources, state.export_events())
    assert restored.pending_updates == ['u3']
    return {'kind': 'hand_confirmed_toy_mechanism_not_detection_score', 'model_calls': 0,
            'rows': rows, 'pending_updates_survive_replay': True}


if __name__ == '__main__':
    print(json.dumps(demo(), ensure_ascii=False, indent=2))
