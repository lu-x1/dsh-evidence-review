"""Offline research kernel for confirmed, typed requirements.

This is NOT a natural-language extractor or a deployed guard. Source matching
checks provenance, not meaning. The caller must separately confirm the typed
interpretation; a model's own `confirmed` label is not such a confirmation.
Only a small affine-expression contract and fit-population contract are
supported. Unsupported mathematics returns unknown, never an inferred pass.
"""
from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
import json
import re
from typing import Mapping


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class Source:
    id: str
    role: str
    text: str


@dataclass(frozen=True)
class Citation:
    source_id: str
    quote: str


@dataclass(frozen=True, order=True)
class Term:
    feature: str
    unit: str
    reference_population: str
    transforms: tuple[str, ...] = ()


@dataclass(frozen=True)
class Formula:
    expression: str
    bindings: Mapping[str, Term]
    output_unit: str


@dataclass(frozen=True)
class Spec:
    formula: Formula | None = None
    fit_population: str | None = None


@dataclass(frozen=True)
class Rule:
    id: str
    version: int
    scope: str
    spec: Spec
    citation: Citation
    # A scoped exception is bound to the inherited version it modifies.
    parent_version: int | None = None


@dataclass(frozen=True)
class Finding:
    component: str
    status: str
    reason: str


@dataclass(frozen=True)
class Check:
    rule_id: str
    status: str
    findings: tuple[Finding, ...]
    requirement: Rule | None
    implementation: Citation | None
    stage: str


def aggregate(statuses):
    statuses = tuple(statuses)
    if any(v not in {'conflict', 'unknown', 'consistent'} for v in statuses):
        raise ContractError('invalid_check_status')
    if 'conflict' in statuses:
        return 'conflict'
    if not statuses or 'unknown' in statuses:
        return 'unknown'
    return 'consistent'


def _term(value):
    if not isinstance(value, dict) or set(value) - {'feature', 'unit', 'reference_population', 'transforms'}:
        raise ContractError('unknown_term_field')
    required = [value.get(k) for k in ('feature', 'unit', 'reference_population')]
    transforms = value.get('transforms', [])
    if (not all(isinstance(v, str) and v for v in required)
            or not isinstance(transforms, (list, tuple))
            or not all(isinstance(v, str) and v for v in transforms)):
        raise ContractError('invalid_term')
    return Term(*required, tuple(transforms))


def _spec(value, populations):
    if not isinstance(value, dict) or set(value) - {'formula', 'fit_population'}:
        raise ContractError('invalid_spec')
    formula = value.get('formula')
    fit = value.get('fit_population')
    if formula is None and fit is None:
        raise ContractError('empty_spec')
    if fit is not None and fit not in populations:
        raise ContractError('unknown_fit_population')
    if formula is not None:
        if (not isinstance(formula, dict) or set(formula) != {'expression', 'bindings', 'output_unit'}
                or not isinstance(formula['expression'], str)
                or not isinstance(formula['bindings'], dict)
                or len(formula['bindings']) > 64
                or not isinstance(formula['output_unit'], str) or not formula['output_unit']):
            raise ContractError('invalid_formula')
        bindings = {k: _term(v) for k, v in formula['bindings'].items()}
        if any(v.reference_population not in populations for v in bindings.values()):
            raise ContractError('unknown_term_population')
        formula = Formula(formula['expression'], bindings, formula['output_unit'])
    return Spec(formula, fit)


def affine(formula):
    """Exact rational normalization, without eval or symbolic guesses.

    Terms already encode independently confirmed feature, unit, transform order
    and reference population. This checks the specified operation contract,
    not extensional equality on one particular dataset or dimensional algebra.
    """
    expression = formula.expression
    if len(expression) > 4096:
        raise ContractError('expression_too_large')
    try:
        tree = ast.parse(expression, mode='eval')
    except (SyntaxError, RecursionError, ValueError):
        raise ContractError('unsupported_expression') from None
    if sum(1 for _ in ast.walk(tree)) > 128:
        raise ContractError('expression_too_large')

    def scale(value, factor):
        constant, terms = value
        return constant * factor, {k: v * factor for k, v in terms.items() if v * factor}

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            literal = ast.get_source_segment(expression, node)
            if len(literal) > 64:
                raise ContractError('constant_too_large')
            exponent = re.search(r'[eE]([+-]?\d+)$', literal.replace('_', ''))
            if exponent and abs(int(exponent.group(1))) > 256:
                raise ContractError('constant_too_large')
            try:
                number = Fraction(literal.replace('_', ''))
            except (ValueError, OverflowError):
                raise ContractError('unsupported_constant') from None
            if max(number.numerator.bit_length(), number.denominator.bit_length()) > 1024:
                raise ContractError('constant_too_large')
            return number, {}
        if isinstance(node, ast.Name) and node.id in formula.bindings:
            return Fraction(0), {formula.bindings[node.id]: Fraction(1)}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return scale(visit(node.operand), -1 if isinstance(node.op, ast.USub) else 1)
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                right = scale(right, -1 if isinstance(node.op, ast.Sub) else 1)
                terms = dict(left[1])
                for key, value in right[1].items():
                    terms[key] = terms.get(key, Fraction(0)) + value
                return left[0] + right[0], {k: v for k, v in terms.items() if v}
            if isinstance(node.op, ast.Mult):
                if not right[1]:
                    return scale(left, right[0])
                if not left[1]:
                    return scale(right, left[0])
            if isinstance(node.op, ast.Div) and not right[1] and right[0]:
                return scale(left, 1 / right[0])
        raise ContractError('unsupported_expression')

    try:
        return visit(tree.body)
    except RecursionError:
        raise ContractError('expression_too_large') from None


class RequirementState:
    """Append-only accepted events; no automatic update from agent output."""
    def __init__(self, sources):
        sources = tuple(sources)
        if len({v.id for v in sources}) != len(sources):
            raise ContractError('duplicate_source')
        self.sources = {v.id: v for v in sources}
        self.source_order = {v.id: i for i, v in enumerate(sources)}
        self.populations = {}
        self.rules = {}
        self.events = []
        self.pending_updates = []
        self._last_source = -1

    def citation(self, value, roles):
        if not isinstance(value, dict) or set(value) != {'source_id', 'quote'}:
            raise ContractError('invalid_citation')
        citation = Citation(**value)
        if not isinstance(citation.source_id, str) or not isinstance(citation.quote, str):
            raise ContractError('invalid_citation')
        source = self.sources.get(citation.source_id)
        if (source is None or source.role not in roles or not citation.quote
                or citation.quote not in source.text):
            raise ContractError('untrusted_or_unmatched_source')
        return citation

    def apply(self, event):
        """Reject ambiguous/unconfirmed proposals without changing old state."""
        event = deepcopy(event)
        if not isinstance(event, dict):
            raise ContractError('invalid_event_fields')
        kind = event.get('kind')
        common = {'id', 'kind', 'citation', 'semantic_status'}
        extra = ({'population', 'parent'} if kind == 'population' else
                 set() if kind == 'begin_update' else
                 {'resolved_sources'} if kind == 'end_update' else
                 {'rule_id', 'scope', 'spec'} if kind == 'add' else
                 {'rule_id', 'scope', 'spec', 'expected_version'})
        if kind not in {'population', 'add', 'replace', 'exception', 'begin_update', 'end_update'} or set(event) != common | extra:
            raise ContractError('invalid_event_fields')
        if event['semantic_status'] != 'confirmed':
            raise ContractError('interpretation_not_confirmed')
        if kind in {'replace', 'exception'} and (type(event['expected_version']) is not int or event['expected_version'] < 1):
            raise ContractError('invalid_update_version')
        if not isinstance(event['id'], str) or not event['id'] or any(v['id'] == event['id'] for v in self.events):
            raise ContractError('duplicate_or_missing_event_id')
        citation = self.citation(event['citation'], {'user'})
        source_index = self.source_order[citation.source_id]
        if source_index < self._last_source:
            raise ContractError('out_of_order_update')
        if kind == 'begin_update':
            if citation.source_id in self.pending_updates:
                raise ContractError('user_update_already_pending')
            self.pending_updates.append(citation.source_id)
        elif kind == 'end_update':
            if (not self.pending_updates or event['resolved_sources'] != self.pending_updates
                    or citation.source_id != self.pending_updates[-1]):
                raise ContractError('all_pending_user_updates_must_be_resolved')
            self.pending_updates.clear()
        elif kind == 'population':
            population, parent = event['population'], event['parent']
            if not isinstance(population, str) or not population or population in self.populations:
                raise ContractError('duplicate_or_invalid_population')
            if parent is not None and parent not in self.populations:
                raise ContractError('unknown_parent_population')
            # A filter/view creates a derived scope. It never refits a rule.
            self.populations[population] = parent
        else:
            rid, scope = event['rule_id'], event['scope']
            if not isinstance(rid, str) or not rid or scope not in self.populations:
                raise ContractError('invalid_rule_or_scope')
            spec = _spec(event['spec'], self.populations)
            current = self.rules.get((rid, scope))
            inherited, inherited_reason = self.resolve(rid, self.populations[scope])
            parent_version = None
            if kind == 'add':
                if any(key[0] == rid for key in self.rules):
                    raise ContractError('rule_already_exists')
            elif kind == 'exception':
                if current is not None or inherited is None or inherited_reason:
                    raise ContractError('exception_requires_current_inherited_rule')
                if event['expected_version'] != inherited.version:
                    raise ContractError('stale_update_version')
                parent_version = inherited.version
            else:
                if current is None or event['expected_version'] != current.version:
                    raise ContractError('stale_or_missing_replacement')
                if current.parent_version is not None:
                    if inherited is None or inherited_reason:
                        raise ContractError('replacement_requires_resolved_parent')
                    parent_version = inherited.version
            version = 1 + max((r.version for (key, _), r in self.rules.items() if key == rid), default=0)
            self.rules[(rid, scope)] = Rule(rid, version, scope, spec, citation, parent_version)
        self.events.append(event)
        self._last_source = source_index

    def resolve(self, rule_id, scope):
        if scope is None:
            return None, 'missing_rule'
        if scope not in self.populations:
            return None, 'unknown_scope'
        rule = self.rules.get((rule_id, scope))
        parent = self.populations[scope]
        if rule is None:
            return self.resolve(rule_id, parent)
        if rule.parent_version is not None:
            inherited, reason = self.resolve(rule_id, parent)
            if reason or inherited.version != rule.parent_version:
                return rule, 'exception_needs_reconfirmation_after_parent_update'
        return rule, None

    def check(self, rule_id, scope, observed, citation, *, semantic_status, stage='proposed'):
        if stage not in {'proposed', 'observed'}:
            raise ContractError('invalid_implementation_stage')
        rule, reason = self.resolve(rule_id, scope)
        if self.pending_updates:
            reason = 'new_user_update_not_yet_resolved'
        if reason:
            return Check(rule_id, 'unknown', (Finding('state', 'unknown', reason),), rule, None, stage)
        try:
            evidence = self.citation(citation, {'assistant', 'tool'})
            if semantic_status != 'confirmed':
                raise ContractError('implementation_interpretation_not_confirmed')
            actual = _spec(observed, self.populations)
        except (ContractError, TypeError, KeyError) as error:
            return Check(rule_id, 'unknown', (Finding('evidence', 'unknown', str(error)),), rule, None, stage)
        findings = []
        if rule.spec.fit_population is not None:
            if actual.fit_population is None:
                findings.append(Finding('fit_population', 'unknown', 'implementation_fit_population_missing'))
            else:
                same = rule.spec.fit_population == actual.fit_population
                findings.append(Finding('fit_population', 'consistent' if same else 'conflict',
                    'fit_population_matches' if same else 'fit_population_changed_without_authorized_update'))
        if rule.spec.formula is not None:
            try:
                if actual.formula is None:
                    raise ContractError('implementation_formula_missing')
                expected_form, actual_form = affine(rule.spec.formula), affine(actual.formula)
                same = expected_form == actual_form and rule.spec.formula.output_unit == actual.formula.output_unit
                findings.append(Finding('formula', 'consistent' if same else 'conflict',
                    'affine_contract_equivalent' if same else 'confirmed_affine_contract_differs'))
            except ContractError as error:
                findings.append(Finding('formula', 'unknown', str(error)))
        return Check(rule_id, aggregate(v.status for v in findings), tuple(findings), rule, evidence, stage)

    def export_events(self):
        return json.dumps(self.events, ensure_ascii=False, sort_keys=True, indent=2) + '\n'

    @classmethod
    def replay(cls, sources, event_json):
        state = cls(sources)
        for event in json.loads(event_json):
            state.apply(event)
        return state


def reminder(checks):
    """Confirmed problems only; unresolved checks cannot cancel a conflict."""
    checks = tuple(checks)
    issues = []
    for check in checks:
        if check.status == 'conflict':
            issues.append({'rule_id': check.rule_id, 'version': check.requirement.version,
                'scope': check.requirement.scope, 'stage': check.stage,
                'requirement_source': vars(check.requirement.citation),
                'implementation_source': vars(check.implementation),
                'conflicts': [vars(v) for v in check.findings if v.status == 'conflict'],
                'instruction': '请核对上述要求与实现的差异，并按当前有效要求修正；其他尚未查清的项目另行保留。'})
    return {'assessment': aggregate(v.status for v in checks), 'issues': issues}
