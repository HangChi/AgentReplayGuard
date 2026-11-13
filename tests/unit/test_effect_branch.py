from __future__ import annotations

from agentreplayguard import EffectStatus
from agentreplayguard.effects import EffectRecord, EffectStore


def test_effect_record_has_branch_id_default_none():
    record = EffectRecord(
        effect_id="eff-000001",
        sequence=1,
        effect_type="refund",
        business_key="R-1",
        params_hash="h",
        idempotency_key_hash=None,
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
    )
    assert record.branch_id is None


def test_effect_record_branch_id_assignable():
    record = EffectRecord(
        effect_id="eff-000001",
        sequence=1,
        effect_type="refund",
        business_key="R-1",
        params_hash="h",
        idempotency_key_hash=None,
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
        branch_id="notify",
    )
    assert record.branch_id == "notify"


def test_effect_record_branch_id_does_not_affect_equality_fields():
    """branch_id 是普通字段，不改变其余字段的相等性。"""
    a = EffectRecord(
        effect_id="eff-000001",
        sequence=1,
        effect_type="refund",
        business_key="R-1",
        params_hash="h",
        idempotency_key_hash=None,
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
        branch_id="notify",
    )
    b = EffectRecord(
        effect_id="eff-000001",
        sequence=1,
        effect_type="refund",
        business_key="R-1",
        params_hash="h",
        idempotency_key_hash=None,
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
        branch_id="deduct",
    )
    # 只有 branch_id 不同 → 不相等（字段参与 dataclass 相等性）
    assert a != b
    # 其余字段完全相同（排除 branch_id 后逻辑身份一致）
    assert a.effect_id == b.effect_id
    assert a.business_key == b.business_key
