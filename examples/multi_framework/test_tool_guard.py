"""框架无关的工具函数级测试：guard.effect 装饰任意 callable 的记账与故障检测。

这是 007 的核心——证明「工具函数是纯 Python callable，guard.effect 装饰即可复用全部能力」，
对 OpenAI Agents SDK / CrewAI / AutoGen 通用。
"""

from __future__ import annotations

import asyncio

from agentreplayguard import (
    FaultKind,
    FaultPlan,
    FaultRule,
    NoDuplicateEffects,
    Scenario,
)


def test_sync_tool_records_committed():
    scenario = Scenario("sync-tool", seed=0, invariants=[NoDuplicateEffects("refund")])
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id")
    def refund(refund_id: str, amount_cents: int) -> str:
        return f"refunded {refund_id}"

    refund("R-1", 100)

    record = scenario.effects.records[0]
    assert record.status.value == "committed"
    assert record.business_key == "R-1"


def test_async_tool_records_committed():
    scenario = Scenario("async-tool", seed=0, invariants=[NoDuplicateEffects("refund")])
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id")
    async def refund(refund_id: str) -> str:
        return f"refunded {refund_id}"

    asyncio.run(refund("R-2"))

    record = scenario.effects.records[0]
    assert record.status.value == "committed"
    assert record.business_key == "R-2"


def test_tool_lost_ack_detected_without_idempotency():
    scenario = Scenario(
        "tool-lost-ack",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id")
    def refund(refund_id: str) -> str:
        return f"refunded {refund_id}"

    for _ in range(2):
        try:
            refund("R-1")
        except TimeoutError:
            continue

    report = scenario.finish()
    assert not report.ok
    assert scenario.effects.committed_count("refund") == 2


def test_tool_idempotency_folds():
    scenario = Scenario(
        "tool-idem",
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

    # 幂等键值用位置参数传入（与 examples/refund/tools.py 约定一致）
    for _ in range(2):
        try:
            refund("R-1", "ik-1")
        except TimeoutError:
            continue

    report = scenario.finish()
    assert report.ok
    assert scenario.effects.committed_count("refund") == 1


def test_tool_before_commit_fault_not_committed():
    scenario = Scenario(
        "tool-before",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_BEFORE_COMMIT, effect_type="refund", attempt=1)]
        ),
    )
    guard = scenario.guard()
    called = []

    @guard.effect("refund", key="refund_id")
    def refund(refund_id: str) -> str:
        called.append(refund_id)
        return f"refunded {refund_id}"

    import pytest

    with pytest.raises(TimeoutError):
        refund("R-1")

    assert called == []  # 提交前故障不执行函数
    assert scenario.effects.records[0].status.value == "not_committed"
