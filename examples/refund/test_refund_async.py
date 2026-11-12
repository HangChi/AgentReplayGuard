"""异步验收：lost-ack 重试与幂等键在异步路径下结论一致。"""

from __future__ import annotations

import asyncio

import pytest

from agentreplayguard import EffectStatus, FaultKind, FaultPlan, FaultRule, Scenario
from agentreplayguard.adapters.langgraph import LangGraphAdapter
from agentreplayguard.services.refund import SimulatedRefundService

from .graph_async import build_async_graph
from .tools_async import make_async_tools


def _lost_ack_scenario() -> Scenario:
    return Scenario(
        "refund-lost-ack-async",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
    )


def test_async_duplicate_is_detected():
    scenario = _lost_ack_scenario()
    refund, _notify, service = make_async_tools(scenario)

    async def run() -> None:
        with pytest.raises(TimeoutError):
            await refund("R-1", 100)
        await refund("R-1", 100)

    asyncio.run(run())

    report = scenario.finish()
    committed = [
        record
        for record in report.effects
        if record.effect_type == "refund" and record.status is EffectStatus.COMMITTED
    ]
    assert len(committed) == 2
    assert [record.attempt for record in committed] == [1, 2]
    assert service.count() == 2


def test_async_graph_duplicate_is_detected(lost_ack_scenario, retry_policy):
    refund, notify, service = make_async_tools(lost_ack_scenario)
    graph = build_async_graph(refund, notify, retry_policy=retry_policy)
    adapter = LangGraphAdapter(lost_ack_scenario, graph)

    asyncio.run(adapter.ainvoke({"refund_id": "R-1", "amount_cents": 100}))

    report = lost_ack_scenario.finish()
    assert not report.ok
    assert service.count() == 2
    assert len(report.run_segments) == 1


def test_async_idempotent_single_refund():
    scenario = Scenario("refund-idempotent-async", seed=0)
    refund, _notify, service = make_async_tools(scenario)

    async def run() -> None:
        await refund("R-2", 200, "key-2")
        await refund("R-2", 200, "key-2")

    asyncio.run(run())

    report = scenario.finish()
    assert report.ok
    assert scenario.effects.committed_count("refund") == 1
    assert service.count() == 1
    assert isinstance(service, SimulatedRefundService)
