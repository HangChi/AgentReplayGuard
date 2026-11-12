"""US5：CustomInvariant 三态与 MaxEffectCount 边界（max_count=0）。"""

from __future__ import annotations

import pytest

from agentreplayguard import CustomInvariant, MaxEffectCount, ScenarioConfigError
from agentreplayguard.effects import EffectStore


def test_custom_invariant_passes():
    store = EffectStore()
    assert CustomInvariant("always", lambda view: True).check(store) == []


def test_custom_invariant_fails_with_message():
    store = EffectStore()
    result = CustomInvariant(
        "exactly_one",
        lambda view: view.committed_count("refund") == 1,
        message="expected exactly one refund",
    ).check(store)
    assert len(result) == 1
    assert result[0].invariant_name == "exactly_one"
    assert result[0].expected is True
    assert result[0].actual is False
    assert result[0].message == "expected exactly one refund"


def test_custom_invariant_raises_is_violation():
    store = EffectStore()

    def boom(view):
        raise RuntimeError("boom")

    result = CustomInvariant("boom", boom).check(store)
    assert len(result) == 1
    assert result[0].expected == "no exception"
    assert result[0].actual == "RuntimeError"
    assert "RuntimeError" in result[0].message


def test_custom_invariant_requires_name():
    with pytest.raises(ScenarioConfigError):
        CustomInvariant("", lambda view: True)


def test_max_effect_count_zero_boundary(add_committed):
    store = EffectStore()
    assert MaxEffectCount("refund", 0).check(store) == []

    add_committed(store, "refund", "R-1")
    result = MaxEffectCount("refund", 0).check(store)
    assert len(result) == 1
    assert result[0].expected == 0
    assert result[0].actual == 1


def test_max_effect_count_requires_non_negative():
    with pytest.raises(ScenarioConfigError):
        MaxEffectCount("refund", -1)
