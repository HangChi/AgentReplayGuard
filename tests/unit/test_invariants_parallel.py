"""NoDuplicateEffects 在带 branch_id 记录上的行为。"""

from __future__ import annotations

from agentreplayguard import EffectStatus
from agentreplayguard.effects import EffectStore
from agentreplayguard.invariants import NoDuplicateEffects


def _add(store, *, branch_id, params_hash="h", idem=None):
    store._append(
        __import__("agentreplayguard").effects.EffectRecord(
            effect_id=store._next_effect_id(),
            sequence=store._next_sequence(),
            effect_type="refund",
            business_key="R-1",
            params_hash=params_hash,
            idempotency_key_hash=idem,
            attempt=1,
            status=EffectStatus.COMMITTED,
            fault=None,
            error_type=None,
            error_message=None,
            run_id=None,
            thread_id=None,
            checkpoint_id=None,
            started_tick=0,
            ended_tick=1,
            branch_id=branch_id,
        )
    )


def test_no_duplicate_detects_parallel_duplicate():
    store = EffectStore()
    _add(store, branch_id="b")
    _add(store, branch_id="c")

    violations = NoDuplicateEffects("refund").check(store)
    assert len(violations) == 1
    assert violations[0].actual == 2


def test_no_duplicate_ignores_branch_id_in_dedup():
    """branch_id 不参与去重口径：同 key 不同 branch 仍计为重复。"""
    store = EffectStore()
    _add(store, branch_id="b")
    _add(store, branch_id="c")

    assert store.committed_count("refund") == 2


def test_no_duplicate_idempotency_folds_parallel():
    store = EffectStore()
    _add(store, branch_id="b", idem="ik-1")
    _add(store, branch_id="c", idem="ik-1")

    assert store.committed_count("refund") == 1
    assert NoDuplicateEffects("refund").check(store) == []


def test_no_duplicate_parameter_mismatch_detected():
    """相同幂等键 + 不同参数 → parameter_mismatch。"""
    store = EffectStore()
    _add(store, branch_id="b", idem="ik-1", params_hash="h1")
    _add(store, branch_id="c", idem="ik-1", params_hash="h2")

    violations = NoDuplicateEffects("refund").check(store)
    kinds = {v.message.split(":")[0] for v in violations}
    assert "parameter_mismatch" in kinds
