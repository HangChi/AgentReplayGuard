"""回归测试：guard.effect 配置参数（key/idempotency_key）与函数实参同名时的关键字传参。

复现 bug：`@guard.effect(..., idempotency_key="idempotency_key")` 装饰的函数若本身有同名
参数 `idempotency_key`，调用时用关键字传参，会抛 `TypeError: got multiple values for
keyword argument`。同样的问题存在于 `key="key"` 配置。
"""

from __future__ import annotations

import asyncio

from agentreplayguard import NoDuplicateEffects, Scenario


def test_effect_idempotency_key_keyword_arg_no_collision():
    """幂等键配置名为 'idempotency_key'，函数也有同名参数，关键字传参不冲突。"""
    scenario = Scenario("sync", seed=0, invariants=[NoDuplicateEffects("refund")])
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id", idempotency_key="idempotency_key")
    def refund(refund_id: str, idempotency_key: str | None = None) -> str:
        return f"refunded {refund_id}"

    # 关键字传幂等键值（此前会抛 TypeError）
    result = refund(refund_id="R-1", idempotency_key="ik-1")

    assert result == "refunded R-1"
    record = scenario.effects.records[0]
    assert record.status.value == "committed"
    assert record.business_key == "R-1"
    assert record.idempotency_key_hash is not None


def test_effect_key_keyword_arg_no_collision():
    """key 配置名为 'key'，函数也有同名参数 'key'，关键字传参不冲突。"""
    scenario = Scenario("sync-key", seed=0, invariants=[NoDuplicateEffects("op")])
    guard = scenario.guard()

    @guard.effect("op", key="key")
    def op(key: str) -> str:
        return f"op {key}"

    result = op(key="K-1")

    assert result == "op K-1"
    record = scenario.effects.records[0]
    assert record.business_key == "K-1"


def test_effect_async_idempotency_key_keyword_arg_no_collision():
    """异步路径同样不冲突。"""
    scenario = Scenario("async", seed=0, invariants=[NoDuplicateEffects("refund")])
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id", idempotency_key="idempotency_key")
    async def refund(refund_id: str, idempotency_key: str | None = None) -> str:
        return f"refunded {refund_id}"

    result = asyncio.run(refund(refund_id="R-2", idempotency_key="ik-2"))

    assert result == "refunded R-2"
    record = scenario.effects.records[0]
    assert record.idempotency_key_hash is not None


def test_effect_idempotency_key_collision_with_retry_still_detects_duplicate():
    """撞名修复后，幂等键 + lost-ack 重试仍正确折叠（不回归）。"""
    from agentreplayguard import FaultKind, FaultPlan, FaultRule

    scenario = Scenario(
        "retry",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id", idempotency_key="idempotency_key")
    def refund(refund_id: str, idempotency_key: str | None = None) -> str:
        return f"refunded {refund_id}"

    for _ in range(2):
        try:
            refund(refund_id="R-1", idempotency_key="ik-1")
        except TimeoutError:
            continue

    report = scenario.finish()
    assert report.ok
    assert scenario.effects.committed_count("refund") == 1
