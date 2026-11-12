from __future__ import annotations

import pytest

from agentreplayguard import FaultKind, FaultPlan, FaultRule, ScenarioConfigError
from agentreplayguard.faults import FaultInjector, is_before_commit


def test_selector_required():
    with pytest.raises(ScenarioConfigError):
        FaultRule(kind=FaultKind.TIMEOUT_BEFORE_COMMIT)


def test_times_validation():
    with pytest.raises(ScenarioConfigError):
        FaultRule(kind=FaultKind.SERVER_ERROR, effect_type="refund", times=0)


def test_probability_validation():
    with pytest.raises(ScenarioConfigError):
        FaultRule(kind=FaultKind.SERVER_ERROR, effect_type="refund", probability=1.5)


def test_before_commit_classification():
    assert is_before_commit(FaultKind.TIMEOUT_BEFORE_COMMIT)
    assert is_before_commit(FaultKind.CONNECTION_RESET)
    assert is_before_commit(FaultKind.SERVER_ERROR)
    assert not is_before_commit(FaultKind.TIMEOUT_AFTER_COMMIT)
    assert not is_before_commit(FaultKind.PARTIAL_SUCCESS)


def test_first_matching_rule_wins():
    plan = FaultPlan(
        [
            FaultRule(kind=FaultKind.SERVER_ERROR, effect_type="refund"),
            FaultRule(kind=FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund"),
        ]
    )
    injector = FaultInjector(plan, seed=0)
    directive = injector.next_directive("refund", "R-1", 1)
    assert directive is not None
    assert directive.kind is FaultKind.SERVER_ERROR


def test_times_exhausted_continues_to_next_rule():
    plan = FaultPlan(
        [
            FaultRule(kind=FaultKind.SERVER_ERROR, effect_type="refund", times=1),
            FaultRule(kind=FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund"),
        ]
    )
    injector = FaultInjector(plan, seed=0)
    first = injector.next_directive("refund", "R-1", 1)
    second = injector.next_directive("refund", "R-1", 2)
    assert first is not None
    assert second is not None
    assert first.kind is FaultKind.SERVER_ERROR
    assert second.kind is FaultKind.TIMEOUT_AFTER_COMMIT


def test_no_matching_rule_returns_none():
    plan = FaultPlan([FaultRule(kind=FaultKind.SERVER_ERROR, effect_type="notify")])
    injector = FaultInjector(plan, seed=0)
    assert injector.next_directive("refund", "R-1", 1) is None


def test_probability_deterministic_with_seed():
    def run(seed):
        plan = FaultPlan(
            [FaultRule(kind=FaultKind.SERVER_ERROR, effect_type="refund", probability=0.5)]
        )
        injector = FaultInjector(plan, seed=seed)
        return [injector.next_directive("refund", "R-1", i) for i in range(1, 6)]

    assert run(0) == run(0)
    assert run(1) == run(1)
