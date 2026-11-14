"""ConcurrentCommitDetected：并发提交判定（区间重叠）。"""

from __future__ import annotations

import asyncio

from agentreplayguard import Scenario
from agentreplayguard.invariants import ConcurrentCommitDetected


def test_concurrent_gather_same_key_detected():
    sc = Scenario("cc", seed=0, invariants=[ConcurrentCommitDetected("refund")])
    guard = sc.guard()

    async def refund():
        await asyncio.sleep(0.01)
        return "ok"

    async def run():
        await asyncio.gather(
            guard.acall("refund", refund, key=lambda a: "ORDER-1"),
            guard.acall("refund", refund, key=lambda a: "ORDER-1"),
        )

    asyncio.run(run())
    report = sc.finish()
    assert not report.ok
    assert any(v.invariant_name == "concurrent_commit:refund" for v in report.violations)


def test_concurrent_sequential_same_key_not_concurrent():
    sc = Scenario("seq", seed=0, invariants=[ConcurrentCommitDetected("refund")])
    guard = sc.guard()

    async def refund():
        return "ok"

    async def run():
        await guard.acall("refund", refund, key=lambda a: "ORDER-1")
        await guard.acall("refund", refund, key=lambda a: "ORDER-1")

    asyncio.run(run())
    report = sc.finish()
    # 顺序执行：不报并发违规（但 NoDuplicateEffects 若注册会报重复）
    assert all(v.invariant_name != "concurrent_commit:refund" for v in report.violations)


def test_concurrent_different_keys_no_violation():
    sc = Scenario("dk", seed=0, invariants=[ConcurrentCommitDetected("refund")])
    guard = sc.guard()

    async def refund():
        await asyncio.sleep(0.01)
        return "ok"

    async def run():
        await asyncio.gather(
            guard.acall("refund", refund, key=lambda a: "K-1"),
            guard.acall("refund", refund, key=lambda a: "K-2"),
        )

    asyncio.run(run())
    report = sc.finish()
    assert report.ok


def test_concurrent_overlap_via_ticks():
    """直接构造重叠 tick 记录，验证区间判定逻辑。"""
    sc = Scenario("ticks", seed=0, invariants=[ConcurrentCommitDetected("refund")])
    guard = sc.guard()

    # 用两个并发 gather 制造重叠区间（依赖 asyncio 交错）
    async def slow():
        await asyncio.sleep(0.02)
        return "ok"

    async def run():
        await asyncio.gather(
            guard.acall("refund", slow, key=lambda a: "ORDER-1"),
            guard.acall("refund", slow, key=lambda a: "ORDER-1"),
        )

    asyncio.run(run())
    report = sc.finish()
    assert not report.ok


def test_any_overlap_sorted_scan_detects_non_adjacent_overlap():
    """排序扫描的完备性回归：重叠可能发生在非相邻（按 started 排序）记录之间。"""
    from agentreplayguard.invariants import _any_overlap

    def record(effect_id, started, ended):
        from agentreplayguard import EffectStatus
        from agentreplayguard.effects import EffectRecord

        return EffectRecord(
            effect_id=effect_id,
            sequence=0,
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
            started_tick=started,
            ended_tick=ended,
        )

    # A=[0,10) B=[10,20) C=[5,15) D=[25,30)
    # C 与 A、B 都重叠；D 与任何记录都不重叠。
    group = [
        record("d", 25, 30),
        record("a", 0, 10),
        record("b", 10, 20),
        record("c", 5, 15),
    ]
    assert _any_overlap(group)


def test_any_overlap_sorted_scan_no_false_positive():
    """排序扫描不误报：两两相接但不重叠的区间。"""
    from agentreplayguard.invariants import _any_overlap

    def record(effect_id, started, ended):
        from agentreplayguard import EffectStatus
        from agentreplayguard.effects import EffectRecord

        return EffectRecord(
            effect_id=effect_id,
            sequence=0,
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
            started_tick=started,
            ended_tick=ended,
        )

    # A=[0,10) B=[10,20) C=[20,30)：相接不重叠，不报
    group = [record("a", 0, 10), record("b", 10, 20), record("c", 20, 30)]
    assert not _any_overlap(group)
