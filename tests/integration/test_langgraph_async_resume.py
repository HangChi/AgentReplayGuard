"""US3 集成测试：异步 checkpoint 恢复与 interrupt 重放。"""

from __future__ import annotations

import asyncio

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from agentreplayguard import FaultKind, FaultPlan, FaultRule, NoDuplicateEffects, Scenario
from agentreplayguard.adapters.langgraph import LangGraphAdapter


def _build_resume_graph(scenario):
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id")
    async def refund(refund_id, amount_cents):
        return f"refunded {refund_id}"

    @guard.effect("notify", key="refund_id")
    async def notify(refund_id):
        return f"notified {refund_id}"

    async def do_refund(state):
        await refund(state["refund_id"], state["amount_cents"])
        return state

    async def do_notify(state):
        await notify(state["refund_id"])
        return state

    builder = StateGraph(dict)
    builder.add_node("refund", do_refund)
    builder.add_node("notify", do_notify)
    builder.set_entry_point("refund")
    builder.add_edge("refund", "notify")
    builder.add_edge("notify", "__end__")
    return builder.compile(checkpointer=InMemorySaver())


def _build_interrupt_graph(scenario, *, effect_before_interrupt):
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id")
    async def refund(refund_id, amount_cents):
        return f"refunded {refund_id}"

    async def do_refund(state):
        if effect_before_interrupt:
            await refund(state["refund_id"], state["amount_cents"])
            interrupt({"approval": "needed"})
        else:
            interrupt({"approval": "needed"})
            await refund(state["refund_id"], state["amount_cents"])
        return state

    builder = StateGraph(dict)
    builder.add_node("refund", do_refund)
    builder.set_entry_point("refund")
    builder.add_edge("refund", "__end__")
    return builder.compile(checkpointer=InMemorySaver())


def test_async_resume_re_executes_effect_before_checkpoint():
    scenario = Scenario(
        "async-resume-before",
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )
    adapter = LangGraphAdapter(scenario, _build_resume_graph(scenario))

    with pytest.raises(TimeoutError):
        asyncio.run(adapter.ainvoke({"refund_id": "R-1", "amount_cents": 100}))

    asyncio.run(adapter.aresume())

    report = scenario.finish()
    assert not report.ok
    assert scenario.effects.committed_count("refund") == 2
    assert [segment.run_id for segment in report.run_segments] == ["run-0001", "run-0002"]


def test_async_resume_does_not_re_execute_effect_after_checkpoint():
    scenario = Scenario(
        "async-resume-after",
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="notify", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )
    adapter = LangGraphAdapter(scenario, _build_resume_graph(scenario))

    with pytest.raises(TimeoutError):
        asyncio.run(adapter.ainvoke({"refund_id": "R-1", "amount_cents": 100}))

    asyncio.run(adapter.aresume())

    report = scenario.finish()
    assert report.ok
    assert scenario.effects.committed_count("refund") == 1
    assert [segment.run_id for segment in report.run_segments] == ["run-0001", "run-0002"]


def test_async_interrupt_after_effect_resume_duplicates():
    scenario = Scenario("async-interrupt-effect-before", invariants=[NoDuplicateEffects("refund")])
    adapter = LangGraphAdapter(
        scenario, _build_interrupt_graph(scenario, effect_before_interrupt=True)
    )

    run = asyncio.run(adapter.ainvoke({"refund_id": "R-1", "amount_cents": 100}))
    assert run.segment.interrupted is True
    assert run.interrupts != ()

    asyncio.run(adapter.aresume_interrupt({"approved": True}))

    report = scenario.finish()
    assert not report.ok
    assert scenario.effects.committed_count("refund") == 2


def test_async_interrupt_before_effect_resume_no_duplicate():
    scenario = Scenario("async-interrupt-effect-after", invariants=[NoDuplicateEffects("refund")])
    adapter = LangGraphAdapter(
        scenario, _build_interrupt_graph(scenario, effect_before_interrupt=False)
    )

    run = asyncio.run(adapter.ainvoke({"refund_id": "R-1", "amount_cents": 100}))
    assert run.segment.interrupted is True

    asyncio.run(adapter.aresume_interrupt({"approved": True}))

    report = scenario.finish()
    assert report.ok
    assert scenario.effects.committed_count("refund") == 1
