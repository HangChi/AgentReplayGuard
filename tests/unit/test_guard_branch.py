from __future__ import annotations

from agentreplayguard import Scenario


def _scenario_with_resolver(resolver):
    sc = Scenario("t", seed=0)
    # 通过内部接口注入 branch resolver（适配器层使用同一入口）
    sc._set_branch_resolver(resolver)
    return sc


def test_guard_records_none_branch_by_default():
    sc = Scenario("t", seed=0)
    guard = sc.guard()

    def fn(x: int) -> int:
        return x

    guard.call("op", fn, 1, key=lambda a: "k")
    record = sc.effects.records[0]
    assert record.branch_id is None


def test_guard_records_branch_via_resolver():
    sc = _scenario_with_resolver(lambda: "notify")
    guard = sc.guard()

    def fn(x: int) -> int:
        return x

    guard.call("op", fn, 1, key=lambda a: "k")
    record = sc.effects.records[0]
    assert record.branch_id == "notify"


def test_guard_resolver_called_per_attempt():
    calls: list[str | None] = []
    seen: list[str | None] = []

    def resolver() -> str | None:
        calls.append(seen[-1] if seen else None)
        return seen[-1] if seen else None

    sc = _scenario_with_resolver(resolver)
    guard = sc.guard()

    def fn(x: int) -> int:
        return x

    # 模拟：不同调用期间 resolver 返回不同值
    seen.append("b")
    guard.call("op", fn, 1, key=lambda a: "k1")
    seen.append("c")
    guard.call("op", fn, 2, key=lambda a: "k2")

    records = sc.effects.records
    assert records[0].branch_id == "b"
    assert records[1].branch_id == "c"


def test_async_guard_records_branch():
    import asyncio

    sc = _scenario_with_resolver(lambda: "deduct")
    guard = sc.guard()

    async def fn(x: int) -> int:
        return x

    async def run():
        await guard.acall("op", fn, 1, key=lambda a: "k")

    asyncio.run(run())
    record = sc.effects.records[0]
    assert record.branch_id == "deduct"
