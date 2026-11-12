"""异步验收：checkpoint 恢复与 interrupt 重放。"""

from __future__ import annotations

import asyncio

import pytest

from agentreplayguard import (
    FaultKind,
    FaultPlan,
    FaultRule,
    NoDuplicateEffects,
    Scenario,
)
from agentreplayguard.adapters.langgraph import LangGraphAdapter

from .graph_async import build_interrupt_graph, build_resume_graph
from .tools_async import make_async_tools


def test_async_resume_duplicates_effect_before_checkpoint():
    scenario = Scenario(
        "refund-async-resume",
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )
    refund, notify, service = make_async_tools(scenario)
    adapter = LangGraphAdapter(scenario, build_resume_graph(refund, notify))

    with pytest.raises(TimeoutError):
        asyncio.run(adapter.ainvoke({"refund_id": "R-1", "amount_cents": 100}))
    asyncio.run(adapter.aresume())

    report = scenario.finish()
    assert not report.ok
    assert service.count() == 2
    assert [segment.run_id for segment in report.run_segments] == ["run-0001", "run-0002"]


def test_async_interrupt_replay_before_effect_duplicates():
    scenario = Scenario(
        "refund-async-interrupt",
        invariants=[NoDuplicateEffects("refund")],
    )
    refund, _notify, service = make_async_tools(scenario)
    adapter = LangGraphAdapter(
        scenario, build_interrupt_graph(refund, effect_before_interrupt=True)
    )

    run = asyncio.run(adapter.ainvoke({"refund_id": "R-1", "amount_cents": 100}))
    assert run.segment.interrupted is True

    asyncio.run(adapter.aresume_interrupt({"approved": True}))

    report = scenario.finish()
    assert not report.ok
    assert service.count() == 2
