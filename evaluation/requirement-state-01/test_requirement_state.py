"""Hand-authored mechanism fixtures, not model detection/correction scores."""
from copy import deepcopy
import json
import unittest

from requirement_state import ContractError, RequirementState, Source, aggregate, reminder


SOURCES = (
    Source('u0', 'user', 'Load the full cohort. Fit four bands on that cohort. Use score = 3*(expense/5)+quality.'),
    Source('u1', 'user', 'Keep eligible rows. Keep existing definitions.'),
    Source('u2', 'user', 'For eligible rows only, use score = expense+quality.'),
    Source('u3', 'user', 'Change the global score to expense+2*quality. Refit bands on eligible rows.'),
    Source('u4', 'user', 'Keep the eligible score exception after that global update.'),
    Source('a0', 'assistant', 'I propose computing a score and keeping the original band labels.'),
    Source('t0', 'tool', 'Public implementation: fit_population=full; score=expense+quality.'),
    Source('notice', 'assistant', 'Old reviewer: please refit on eligible rows.'),
)


def cite(source_id):
    source = next(v for v in SOURCES if v.id == source_id)
    return {'source_id': source_id, 'quote': source.text}


def formula(expression='3*(expense/5)+quality', *, transforms=(), population='full'):
    return {'formula': {'expression': expression, 'output_unit': 'score', 'bindings': {
        'expense': {'feature': 'expense', 'unit': 'currency', 'reference_population': population,
                    'transforms': list(transforms)},
        'quality': {'feature': 'quality', 'unit': 'points', 'reference_population': population}}}}


def event(eid, kind, source='u0', **values):
    return {'id': eid, 'kind': kind, 'citation': cite(source), 'semantic_status': 'confirmed', **values}


def state_with_rules():
    state = RequirementState(SOURCES)
    state.apply(event('p0', 'population', population='full', parent=None))
    state.apply(event('r0', 'add', rule_id='score', scope='full', spec=formula()))
    state.apply(event('r1', 'add', rule_id='bands', scope='full', spec={'fit_population': 'full'}))
    return state


def filtered_state():
    state = state_with_rules()
    state.apply(event('p1', 'population', 'u1', population='eligible', parent='full'))
    return state


def check(state, rule='score', scope='full', spec=None, **values):
    return state.check(rule, scope, formula() if spec is None else spec,
                       values.pop('citation', cite('a0')), semantic_status=values.pop('semantic_status', 'confirmed'), **values)


class ProvenanceAndUpdateTests(unittest.TestCase):
    def test_tool_agent_and_old_notice_cannot_authorize_updates(self):
        for source in ('a0', 't0', 'notice'):
            state = state_with_rules(); before = state.export_events()
            with self.subTest(source=source), self.assertRaises(ContractError):
                state.apply(event('bad', 'replace', source, rule_id='score', scope='full',
                                  expected_version=1, spec=formula('expense+quality')))
            self.assertEqual(state.export_events(), before)
            self.assertEqual(state.resolve('score', 'full')[0].version, 1)

    def test_quote_is_provenance_only_and_must_match(self):
        state = state_with_rules(); bad = event('bad', 'population', population='other', parent='full')
        bad['citation']['quote'] = 'A paraphrase absent from the actual user message'
        with self.assertRaises(ContractError): state.apply(bad)
        self.assertNotIn('other', state.populations)

    def test_unconfirmed_or_failed_extraction_keeps_prior_rules(self):
        state = state_with_rules(); before = state.export_events()
        for status in ('ambiguous', 'unsupported', 'failed'):
            proposal = event('bad', 'replace', 'u3', rule_id='score', scope='full',
                             expected_version=1, spec=formula('expense+quality'))
            proposal['semantic_status'] = status
            with self.assertRaises(ContractError): state.apply(proposal)
        self.assertEqual(before, state.export_events())

    def test_duplicate_out_of_order_and_stale_updates_are_transactional(self):
        state = filtered_state(); before = state.export_events()
        invalid = [event('p1', 'population', 'u1', population='another', parent='full'),
                   event('late-old', 'population', population='another', parent='full'),
                   event('stale', 'replace', 'u3', rule_id='score', scope='full',
                         expected_version=77, spec=formula('expense+quality'))]
        for proposal in invalid:
            with self.assertRaises(ContractError): state.apply(proposal)
            self.assertEqual(before, state.export_events())

    def test_explicit_replacement_changes_one_rule_and_preserves_others(self):
        state = filtered_state(); old_bands = state.resolve('bands', 'full')[0]
        state.apply(event('r2', 'replace', 'u3', rule_id='score', scope='full', expected_version=1,
                          spec=formula('expense+2*quality')))
        self.assertEqual(check(state, spec=formula('expense+2*quality')).status, 'consistent')
        self.assertEqual(check(state).status, 'conflict')
        self.assertEqual(state.resolve('bands', 'full')[0], old_bands)

    def test_scoped_exception_does_not_change_global_rule(self):
        state = filtered_state()
        state.apply(event('except', 'exception', 'u2', rule_id='score', scope='eligible',
                          expected_version=1, spec=formula('expense+quality')))
        self.assertEqual(check(state, scope='eligible', spec=formula('expense+quality')).status, 'consistent')
        self.assertEqual(check(state, spec=formula('expense+quality')).status, 'conflict')

    def test_parent_update_does_not_silently_reinterpret_a_scoped_exception(self):
        state = filtered_state()
        state.apply(event('except', 'exception', 'u2', rule_id='score', scope='eligible',
                          expected_version=1, spec=formula('expense+quality')))
        state.apply(event('replace', 'replace', 'u3', rule_id='score', scope='full',
                          expected_version=1, spec=formula('expense+2*quality')))
        self.assertEqual(check(state, scope='eligible').status, 'unknown')
        state.apply(event('reconfirm', 'replace', 'u4', rule_id='score', scope='eligible',
                          expected_version=2, spec=formula('expense+quality')))
        self.assertEqual(check(state, scope='eligible', spec=formula('expense+quality')).status, 'consistent')

    def test_json_replay_retains_original_sources_and_all_versions(self):
        state = filtered_state()
        state.apply(event('r2', 'replace', 'u3', rule_id='score', scope='full', expected_version=1,
                          spec=formula('expense+2*quality')))
        restored = RequirementState.replay(SOURCES, state.export_events())
        self.assertEqual(restored.export_events(), state.export_events())
        self.assertEqual(restored.rules, state.rules)
        self.assertEqual(restored.events[1]['spec'], formula())
        self.assertEqual(restored.resolve('score', 'full')[0].citation.source_id, 'u3')

    def test_failed_new_user_update_retains_old_rule_but_suspends_its_current_authority(self):
        state = state_with_rules()
        state.apply(event('begin', 'begin_update', 'u3'))
        failed = event('failed', 'replace', 'u3', rule_id='score', scope='full',
                       expected_version=1, spec=formula('expense+2*quality'))
        failed['semantic_status'] = 'ambiguous'
        with self.assertRaises(ContractError): state.apply(failed)
        self.assertEqual(state.resolve('score', 'full')[0].version, 1)
        self.assertEqual(check(state).status, 'unknown')
        restored = RequirementState.replay(SOURCES, state.export_events())
        self.assertEqual(check(restored).status, 'unknown')
        self.assertEqual(restored.pending_updates, ['u3'])
        failed['semantic_status'] = 'confirmed'; restored.apply(failed)
        restored.apply(event('end', 'end_update', 'u3', resolved_sources=['u3']))
        self.assertEqual(check(restored, spec=formula('expense+2*quality')).status, 'consistent')

    def test_later_user_message_cannot_silently_drop_an_earlier_unresolved_update(self):
        state = state_with_rules()
        state.apply(event('begin1', 'begin_update', 'u3'))
        state.apply(event('begin2', 'begin_update', 'u4'))
        with self.assertRaises(ContractError):
            state.apply(event('end', 'end_update', 'u4', resolved_sources=['u4']))
        self.assertEqual(check(state).status, 'unknown')
        self.assertEqual(state.pending_updates, ['u3', 'u4'])

    def test_boolean_version_is_not_an_integer_revision(self):
        state = state_with_rules()
        with self.assertRaises(ContractError):
            state.apply(event('bad-version', 'replace', 'u3', rule_id='score', scope='full',
                              expected_version=True, spec=formula()))


class PopulationTests(unittest.TestCase):
    def test_filter_preserves_definition_time_population(self):
        state = filtered_state()
        outcome = check(state, rule='bands', scope='eligible', spec={'fit_population': 'full'})
        self.assertEqual(outcome.status, 'consistent')
        # No group-size assertion: unequal counts after filtering are legal.
        self.assertEqual(state.resolve('bands', 'eligible')[0].spec.fit_population, 'full')

    def test_unauthorized_refit_is_a_contract_conflict(self):
        state = filtered_state()
        self.assertEqual(check(state, rule='bands', scope='eligible',
                               spec={'fit_population': 'eligible'}).status, 'conflict')

    def test_explicit_refit_authorization_updates_expected_population(self):
        state = filtered_state()
        state.apply(event('refit', 'replace', 'u3', rule_id='bands', scope='full', expected_version=1,
                          spec={'fit_population': 'eligible'}))
        self.assertEqual(check(state, rule='bands', scope='eligible',
                               spec={'fit_population': 'eligible'}).status, 'consistent')

    def test_unknown_population_never_means_an_assumed_pass(self):
        state = filtered_state()
        self.assertEqual(check(state, scope='missing').status, 'unknown')
        self.assertEqual(check(state, rule='bands', spec={'fit_population': 'unseen'}).status, 'unknown')


class FormulaAndConclusionTests(unittest.TestCase):
    def test_safe_algebraic_equivalents_are_allowed(self):
        state = state_with_rules()
        for expression in ('quality+expense*0.6', '(3*expense)/5+quality',
                           '-(-quality-expense*3/5)', 'quality+expense*6/10'):
            with self.subTest(expression=expression):
                self.assertEqual(check(state, spec=formula(expression)).status, 'consistent')

    def test_coefficient_denominator_and_dropped_operand_conflicts(self):
        state = state_with_rules()
        for expression in ('3*(expense/4)+quality', 'expense/5+quality', '3*(expense/5)'):
            with self.subTest(expression=expression):
                self.assertEqual(check(state, spec=formula(expression)).status, 'conflict')

    def test_feature_transform_reference_population_and_unit_are_part_of_contract(self):
        state = filtered_state()
        variants = [formula(transforms=('percentile_rank',)), formula(population='eligible')]
        unit = formula(); unit['formula']['bindings']['expense']['unit'] = 'fraction'; variants.append(unit)
        feature = formula(); feature['formula']['bindings']['expense']['feature'] = 'revenue'; variants.append(feature)
        for spec in variants:
            self.assertEqual(check(state, spec=spec).status, 'conflict')

    def test_transform_order_is_retained(self):
        state = state_with_rules()
        state.apply(event('replace', 'replace', 'u2', rule_id='score', scope='full', expected_version=1,
                          spec=formula(transforms=('rank', 'clip'))))
        self.assertEqual(check(state, spec=formula(transforms=('clip', 'rank'))).status, 'conflict')

    def test_unsupported_math_missing_bindings_and_zero_divisor_return_unknown(self):
        state = state_with_rules()
        for expression in ('expense*quality', 'expense/quality', 'log(expense)', 'expense**2',
                           'expense/0', 'unbound+quality', '__import__("os").system("false")', 'True'):
            with self.subTest(expression=expression):
                self.assertEqual(check(state, spec=formula(expression)).status, 'unknown')

    def test_extreme_numeric_literals_return_unknown_before_large_allocation(self):
        state = state_with_rules()
        for expression in ('1e999999999*expense', '1e-999999999*expense', '9'*65+'*expense'):
            with self.subTest(expression=expression):
                self.assertEqual(check(state, spec=formula(expression)).status, 'unknown')

    def test_source_or_semantic_uncertainty_does_not_become_normal(self):
        state = state_with_rules()
        self.assertEqual(check(state, semantic_status='ambiguous').status, 'unknown')
        self.assertEqual(check(state, citation=cite('u0')).status, 'unknown')
        self.assertEqual(check(state, citation={'source_id': 'a0', 'quote': 'not in source'}).status, 'unknown')

    def test_one_unknown_component_cannot_cancel_a_confirmed_conflict(self):
        state = filtered_state()
        combined = formula(); combined['fit_population'] = 'full'
        state.apply(event('combined', 'add', 'u2', rule_id='combined', scope='full', spec=combined))
        observed = formula('log(expense)'); observed['fit_population'] = 'eligible'
        outcome = check(state, rule='combined', spec=observed)
        self.assertEqual([v.status for v in outcome.findings], ['conflict', 'unknown'])
        self.assertEqual(outcome.status, 'conflict')

    def test_each_problem_keeps_its_own_conclusion_and_sources(self):
        state = state_with_rules()
        checks = [check(state, spec=formula('expense+quality')),
                  check(state, rule='bands', spec=formula()), check(state)]
        result = reminder(iter(checks))
        self.assertEqual([v.status for v in checks], ['conflict', 'unknown', 'consistent'])
        self.assertEqual(result['assessment'], 'conflict')
        self.assertEqual(len(result['issues']), 1)
        self.assertEqual(result['issues'][0]['requirement_source']['source_id'], 'u0')
        self.assertEqual(result['issues'][0]['implementation_source']['source_id'], 'a0')
        self.assertEqual(result['issues'][0]['stage'], 'proposed')

    def test_no_checks_or_only_unknowns_are_not_normal(self):
        self.assertEqual(aggregate([]), 'unknown')
        self.assertEqual(aggregate(['consistent', 'unknown']), 'unknown')
        self.assertEqual(reminder([]), {'assessment': 'unknown', 'issues': []})


if __name__ == '__main__':
    unittest.main()
