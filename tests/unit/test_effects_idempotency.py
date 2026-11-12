"""US2 幂等去重口径：有幂等键去重、无幂等键独立计数、参数不一致。"""

from __future__ import annotations

from agentreplayguard import NoDuplicateEffects
from agentreplayguard.effects import EffectStore


def test_same_key_same_params_counts_once(add_committed):
    store = EffectStore()
    add_committed(store, "refund", "R-1", idem_hash="k1", params_hash="a")
    add_committed(store, "refund", "R-1", idem_hash="k1", params_hash="a")

    assert store.committed_count("refund") == 1
    assert NoDuplicateEffects("refund").check(store) == []


def test_same_key_different_params_parameter_mismatch(add_committed):
    store = EffectStore()
    add_committed(store, "refund", "R-1", idem_hash="k1", params_hash="a")
    add_committed(store, "refund", "R-1", idem_hash="k1", params_hash="b")

    result = NoDuplicateEffects("refund").check(store)
    assert len(result) == 1
    assert "parameter_mismatch" in result[0].message


def test_no_key_counts_each_attempt(add_committed):
    store = EffectStore()
    add_committed(store, "refund", "R-1")
    add_committed(store, "refund", "R-1")

    assert store.committed_count("refund") == 2
    result = NoDuplicateEffects("refund").check(store)
    assert len(result) == 1
    assert "duplicate_effects" in result[0].message
