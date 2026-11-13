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
