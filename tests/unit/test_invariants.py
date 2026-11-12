from __future__ import annotations

from agentreplayguard import CustomInvariant, MaxEffectCount, NoDuplicateEffects
from agentreplayguard.effects import EffectStore


def test_no_duplicate_effects_detects_two_commits(add_committed):
    store = EffectStore()
    add_committed(store, "refund", "R-1")
    add_committed(store, "refund", "R-1")

    result = NoDuplicateEffects("refund").check(store)
    assert len(result) == 1
    assert result[0].message.startswith("duplicate_effects")


def test_no_duplicate_effects_same_idempotency_key_passes(add_committed):
    store = EffectStore()
    add_committed(store, "refund", "R-1", idem_hash="k1", params_hash="a")
    add_committed(store, "refund", "R-1", idem_hash="k1", params_hash="a")

    assert NoDuplicateEffects("refund").check(store) == []


def test_no_duplicate_effects_parameter_mismatch(add_committed):
    store = EffectStore()
    add_committed(store, "refund", "R-1", idem_hash="k1", params_hash="a")
    add_committed(store, "refund", "R-1", idem_hash="k1", params_hash="b")

    result = NoDuplicateEffects("refund").check(store)
    assert len(result) == 1
    assert "parameter_mismatch" in result[0].message


def test_no_duplicate_effects_different_keys_is_duplicate(add_committed):
    store = EffectStore()
    add_committed(store, "refund", "R-1", idem_hash="k1")
    add_committed(store, "refund", "R-1", idem_hash="k2")

    result = NoDuplicateEffects("refund").check(store)
    assert len(result) == 1
    assert "duplicate_effects" in result[0].message


def test_max_effect_count_violates(add_committed):
    store = EffectStore()
    add_committed(store, "refund", "R-1")
    add_committed(store, "refund", "R-1")

    result = MaxEffectCount("refund", 1).check(store)
    assert len(result) == 1
    assert result[0].actual == 2
    assert result[0].expected == 1


def test_max_effect_count_boundary_zero(add_committed):
    store = EffectStore()
    add_committed(store, "refund", "R-1")
    result = MaxEffectCount("refund", 0).check(store)
    assert len(result) == 1


def test_custom_invariant_pass_fail_raise():
    store = EffectStore()

    passing = CustomInvariant("pass", lambda view: True)
    assert passing.check(store) == []

    failing = CustomInvariant("fail", lambda view: False)
    failing_result = failing.check(store)
    assert len(failing_result) == 1
    assert failing_result[0].invariant_name == "fail"

    def boom(view):
        raise RuntimeError("boom")

    raising = CustomInvariant("raise", boom)
    raising_result = raising.check(store)
    assert len(raising_result) == 1
    assert "RuntimeError" in raising_result[0].message
