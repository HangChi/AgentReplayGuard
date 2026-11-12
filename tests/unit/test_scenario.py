from __future__ import annotations

import pytest

from agentreplayguard import (
    NoDuplicateEffects,
    Scenario,
    ScenarioConfigError,
    ScenarioStateError,
)


def test_name_required():
    with pytest.raises(ScenarioConfigError):
        Scenario("")


def test_name_length_limit():
    with pytest.raises(ScenarioConfigError):
        Scenario("x" * 81)


def test_seed_must_be_int():
    with pytest.raises(ScenarioConfigError):
        Scenario("s", seed="0")  # type: ignore[arg-type]


def test_duplicate_invariant_names():
    with pytest.raises(ScenarioConfigError):
        Scenario("s", invariants=[NoDuplicateEffects("refund"), NoDuplicateEffects("refund")])


def test_finish_idempotent():
    scenario = Scenario("s")
    first = scenario.finish()
    second = scenario.finish()
    assert first is second


def test_finished_guard_raises_state_error():
    scenario = Scenario("s")
    scenario.finish()

    def fn(refund_id):
        return refund_id

    with pytest.raises(ScenarioStateError):
        scenario.guard().call("refund", fn, refund_id="R-1", key="refund_id")


def test_no_invariants_warns():
    scenario = Scenario("s")
    report = scenario.finish()
    assert report.ok
    assert any("no invariants" in warning for warning in report.warnings)


def test_effects_are_isolated_per_scenario():
    first = Scenario("first")
    second = Scenario("second")
    first.guard().call("refund", lambda refund_id: refund_id, refund_id="R-1", key="refund_id")
    assert len(first.effects.records) == 1
    assert len(second.effects.records) == 0
