"""US1：异步工具的记账与故障注入语义。"""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

from agentreplayguard import (
    EffectStatus,
    FaultKind,
    FaultPlan,
    FaultRule,
    Scenario,
)


def _sha256_params(obj: dict) -> str:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_async_effect_commits_once():
    scenario = Scenario("s")
    guard = scenario.guard()

    async def refund(refund_id, amount_cents):
        return f"refunded {refund_id}"

    result = asyncio.run(
        guard.acall("refund", refund, refund_id="R-1", amount_cents=100, key="refund_id")
    )

    assert result == "refunded R-1"
    record = scenario.effects.records[0]
    assert record.status is EffectStatus.COMMITTED
    assert record.business_key == "R-1"
    assert record.attempt == 1
    assert record.params_hash == _sha256_params({"amount_cents": 100})


def test_async_effect_decorator_supports_async_callable():
    scenario = Scenario("s")

    @scenario.guard().effect("refund", key="refund_id")
    async def refund(refund_id):
        """Async refund."""
        return refund_id

    assert refund.__name__ == "refund"
    assert asyncio.run(refund("R-9")) == "R-9"
    assert scenario.effects.records[0].status is EffectStatus.COMMITTED


def test_async_lost_ack_retry_commits_twice():
    scenario = Scenario(
        "s",
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
    )
    guard = scenario.guard()

    async def refund(refund_id):
        return "ok"

    async def run():
        with pytest.raises(TimeoutError):
            await guard.acall("refund", refund, refund_id="R-1", key="refund_id")
        return await guard.acall("refund", refund, refund_id="R-1", key="refund_id")

    assert asyncio.run(run()) == "ok"
    records = scenario.effects.records
    assert [record.status for record in records] == [
        EffectStatus.COMMITTED,
        EffectStatus.COMMITTED,
    ]
    assert [record.attempt for record in records] == [1, 2]
    assert len({record.params_hash for record in records}) == 1


def test_async_before_commit_fault_does_not_execute():
    scenario = Scenario(
        "s",
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_BEFORE_COMMIT, effect_type="refund", attempt=1)]
        ),
    )
    guard = scenario.guard()
    called = []

    async def refund(refund_id):
        called.append(refund_id)
        return "ok"

    with pytest.raises(TimeoutError):
        asyncio.run(guard.acall("refund", refund, refund_id="R-1", key="refund_id"))

    assert called == []
    record = scenario.effects.records[0]
    assert record.status is EffectStatus.NOT_COMMITTED
    assert record.error_type == "TimeoutError"


def test_async_exception_passthrough_not_committed():
    scenario = Scenario("s")
    guard = scenario.guard()

    async def refund(refund_id):
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(guard.acall("refund", refund, refund_id="R-1", key="refund_id"))

    record = scenario.effects.records[0]
    assert record.status is EffectStatus.NOT_COMMITTED
    assert record.error_type == "ValueError"
    assert record.error_message == "boom"


def test_async_cancellation_records_unknown():
    scenario = Scenario("s")
    guard = scenario.guard()

    async def refund(refund_id):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(guard.acall("refund", refund, refund_id="R-1", key="refund_id"))

    record = scenario.effects.records[0]
    assert record.status is EffectStatus.UNKNOWN
    assert record.error_type == "CancelledError"


def test_acall_accepts_sync_function():
    scenario = Scenario("s")
    guard = scenario.guard()

    def refund(refund_id):
        return refund_id

    result = asyncio.run(guard.acall("refund", refund, refund_id="R-1", key="refund_id"))

    assert result == "R-1"
    assert scenario.effects.records[0].status is EffectStatus.COMMITTED


def test_acall_sync_function_raising_records_not_committed():
    """回归：acall 传入同步 fn 且 fn 自身抛异常时，也必须记账 NOT_COMMITTED。"""
    scenario = Scenario("s")
    guard = scenario.guard()

    def refund(refund_id):
        raise ValueError("boom sync")

    with pytest.raises(ValueError, match="boom sync"):
        asyncio.run(guard.acall("refund", refund, refund_id="R-1", key="refund_id"))

    record = scenario.effects.records[0]
    assert record.status is EffectStatus.NOT_COMMITTED
    assert record.error_type == "ValueError"
    assert record.error_message == "boom sync"


def test_acall_exception_group_records_not_committed():
    """回归：acall 包裹的 fn 通过 asyncio.TaskGroup 抛 ExceptionGroup 时记账 NOT_COMMITTED。"""
    scenario = Scenario("s")
    guard = scenario.guard()

    async def refund(refund_id):
        async with asyncio.TaskGroup() as tg:

            async def inner() -> None:
                raise ValueError("inner boom")

            tg.create_task(inner())

    # ExceptionGroup 是 Exception 的子类（3.11+），可被 except Exception 捕获；
    # 此处用 Exception 兜底断言，保证 3.10 语义一致。
    with pytest.raises(Exception) as excinfo:
        asyncio.run(guard.acall("refund", refund, refund_id="R-1", key="refund_id"))
    assert type(excinfo.value).__name__ == "ExceptionGroup"

    record = scenario.effects.records[0]
    assert record.status is EffectStatus.NOT_COMMITTED
    assert record.error_type == "ExceptionGroup"
