"""US2 集成测试：异步驱动图与同步路径的等价性。"""

from __future__ import annotations

import asyncio

from langgraph.graph import StateGraph
from langgraph.types import RetryPolicy

from agentreplayguard import (
    EffectStatus,
    FaultKind,
    FaultPlan,
    FaultRule,
    NoDuplicateEffects,
    Scenario,
)
from agentreplayguard.adapters.langgraph import LangGraphAdapter


def _retry_policy() -> RetryPolicy:
    return RetryPolicy(
        max_attempts=3,
        retry_on=(TimeoutError,),
        initial_interval=0,
        jitter=False,
    )


def _build_async_graph(scenario):
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
    builder.add_node("refund", do_refund, retry_policy=_retry_policy())
    builder.add_node("notify", do_notify)
    builder.set_entry_point("refund")
    builder.add_edge("refund", "notify")
    builder.add_edge("notify", "__end__")
    return builder.compile()


def _build_sync_graph(scenario):
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id")
    def refund(refund_id, amount_cents):
        return f"refunded {refund_id}"

    @guard.effect("notify", key="refund_id")
    def notify(refund_id):
        return f"notified {refund_id}"

    def do_refund(state):
        refund(state["refund_id"], state["amount_cents"])
        return state

    def do_notify(state):
        notify(state["refund_id"])
        return state

    builder = StateGraph(dict)
    builder.add_node("refund", do_refund, retry_policy=_retry_policy())
    builder.add_node("notify", do_notify)
    builder.set_entry_point("refund")
    builder.add_edge("refund", "notify")
    builder.add_edge("notify", "__end__")
    return builder.compile()


def _lost_ack_scenario(name: str) -> Scenario:
    return Scenario(
        name,
        seed=7,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )


def test_ainvoke_detects_lost_ack_duplicate():
    scenario = _lost_ack_scenario("async-lost-ack")
    adapter = LangGraphAdapter(scenario, _build_async_graph(scenario))

    run = asyncio.run(adapter.ainvoke({"refund_id": "R-1", "amount_cents": 100}))

    report = scenario.finish()
    assert run.segment.run_id == "run-0001"
    assert not report.ok
    assert scenario.effects.committed_count("refund") == 2
    assert [record.attempt for record in report.effects] == [1, 2, 1]


def test_async_mixed_with_sync_node():
    scenario = Scenario("async-mixed")
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id")
    async def refund(refund_id, amount_cents):
        return f"refunded {refund_id}"

    @guard.effect("notify", key="refund_id")
    def notify(refund_id):
        return f"notified {refund_id}"

    async def do_refund(state):
        await refund(state["refund_id"], state["amount_cents"])
        return state

    def do_notify(state):
        notify(state["refund_id"])
        return state

    builder = StateGraph(dict)
    builder.add_node("refund", do_refund)
    builder.add_node("notify", do_notify)
    builder.set_entry_point("refund")
    builder.add_edge("refund", "notify")
    builder.add_edge("notify", "__end__")
    adapter = LangGraphAdapter(scenario, builder.compile())

    asyncio.run(adapter.ainvoke({"refund_id": "R-1", "amount_cents": 100}))

    report = scenario.finish()
    assert report.ok
    assert scenario.effects.committed_count("refund") == 1
    assert scenario.effects.committed_count("notify") == 1


def test_sync_and_async_effects_are_identical():
    def signature(scenario: Scenario):
        return [
            (
                record.effect_type,
                record.status,
                record.attempt,
                record.business_key,
                record.params_hash,
                record.fault,
            )
            for record in scenario.finish().effects
        ]

    for _ in range(20):
        sync_scenario = _lost_ack_scenario("sync")
        sync_adapter = LangGraphAdapter(sync_scenario, _build_sync_graph(sync_scenario))
        sync_adapter.invoke({"refund_id": "R-1", "amount_cents": 100})

        async_scenario = _lost_ack_scenario("async")
        async_adapter = LangGraphAdapter(async_scenario, _build_async_graph(async_scenario))
        asyncio.run(async_adapter.ainvoke({"refund_id": "R-1", "amount_cents": 100}))

        assert signature(sync_scenario) == signature(async_scenario)

    assert all(
        record.status is EffectStatus.COMMITTED
        for record in async_scenario.effects.records
        if record.effect_type == "refund"
    )
