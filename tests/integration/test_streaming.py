"""流式接口集成测试：astream/astream_events 的 effect 归属与故障注入等价。"""

from __future__ import annotations

import asyncio
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from agentreplayguard import (
    FaultKind,
    FaultPlan,
    FaultRule,
    NoDuplicateEffects,
    Scenario,
)
from agentreplayguard.adapters.langgraph import LangGraphAdapter


class State(TypedDict):
    log: Annotated[list[str], operator.add]


def _make_serial_graph(scenario: Scenario):
    guard = scenario.guard()
    g = StateGraph(State)

    def a(s):
        guard.call("op", lambda: None, key=lambda _: "K-A")
        return {"log": ["a"]}

    def b(s):
        guard.call("op", lambda: None, key=lambda _: "K-B")
        return {"log": ["b"]}

    g.add_node("a", a)
    g.add_node("b", b)
    g.add_edge(START, "a")
    g.add_edge("a", "b")
    g.add_edge("b", END)
    return g.compile()


def _make_lost_ack_graph(scenario: Scenario):
    guard = scenario.guard()
    g = StateGraph(State)

    def do_refund(s):
        guard.call("refund", lambda: None, key=lambda _: "ORDER-1")
        return {"log": ["refund"]}

    g.add_node(
        "refund",
        do_refund,
        retry_policy=RetryPolicy(
            max_attempts=2, retry_on=(TimeoutError,), initial_interval=0, jitter=False
        ),
    )
    g.add_edge(START, "refund")
    g.add_edge("refund", END)
    return g.compile()


def _lost_ack_scenario() -> Scenario:
    return Scenario(
        "lost-ack",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )


async def _drain(agen):
    out = []
    async for item in agen:
        out.append(item)
    return out


def test_astream_branch_attribution():
    scenario = Scenario("s", seed=0)
    adapter = LangGraphAdapter(scenario, _make_serial_graph(scenario))

    chunks = asyncio.run(_drain(adapter.astream({"log": []})))

    assert len(chunks) == 2
    records = scenario.effects.records
    assert {r.branch_id for r in records} == {"a", "b"}
    assert {r.run_id for r in records} == {"run-0001"}


def test_astream_lost_ack_detected():
    scenario = _lost_ack_scenario()
    adapter = LangGraphAdapter(scenario, _make_lost_ack_graph(scenario))

    asyncio.run(_drain(adapter.astream({"log": []})))

    report = scenario.finish()
    assert not report.ok
    assert scenario.effects.committed_count("refund") == 2
    # attempt 1 带 fault，attempt 2 无 fault
    statuses = [(r.attempt, r.fault is not None) for r in scenario.effects.for_effect("refund")]
    assert statuses == [(1, True), (2, False)]


def test_astream_before_commit_fault_raises():
    scenario = Scenario(
        "before-commit",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_BEFORE_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )
    guard = scenario.guard()
    g = StateGraph(State)

    def do_refund(s):
        guard.call("refund", lambda: None, key=lambda _: "ORDER-1")
        return {"log": ["refund"]}

    g.add_node("refund", do_refund)
    g.add_edge(START, "refund")
    g.add_edge("refund", END)

    adapter = LangGraphAdapter(scenario, g.compile())

    with __import__("pytest").raises(TimeoutError):
        asyncio.run(_drain(adapter.astream({"log": []})))

    record = scenario.effects.records[0]
    assert record.status.value == "not_committed"


def test_astream_events_branch_attribution():
    scenario = Scenario("s", seed=0)
    adapter = LangGraphAdapter(scenario, _make_serial_graph(scenario))

    events = asyncio.run(_drain(adapter.astream_events({"log": []}, version="v2")))

    assert len(events) > 0
    records = scenario.effects.records
    assert {r.branch_id for r in records} == {"a", "b"}
    report = scenario.finish()
    assert len(report.run_segments) == 1


def test_stream_mode_transparent():
    scenario = Scenario("s", seed=0)
    adapter = LangGraphAdapter(scenario, _make_serial_graph(scenario))

    chunks = asyncio.run(_drain(adapter.astream({"log": []}, stream_mode="updates")))

    assert len(chunks) == 2
    records = scenario.effects.records
    assert len(records) == 2


def test_sync_stream_branch_attribution():
    """同步 stream 与 astream 一样正确归属 branch。"""
    scenario = Scenario("s", seed=0)
    adapter = LangGraphAdapter(scenario, _make_serial_graph(scenario))

    chunks = list(adapter.stream({"log": []}))

    assert len(chunks) == 2
    records = scenario.effects.records
    assert {r.branch_id for r in records} == {"a", "b"}
    assert {r.run_id for r in records} == {"run-0001"}


def test_sync_stream_vs_astream_parity():
    """同步 stream 与异步 astream 的 effect 记录数/状态/attempt/branch 一致。"""

    def run_stream():
        sc = Scenario("s", seed=0)
        ad = LangGraphAdapter(sc, _make_serial_graph(sc))
        list(ad.stream({"log": []}))
        return sc.effects.records

    async def run_astream():
        sc = Scenario("s", seed=0)
        ad = LangGraphAdapter(sc, _make_serial_graph(sc))
        await _drain(ad.astream({"log": []}))
        return sc.effects.records

    stream_records = run_stream()
    astream_records = asyncio.run(run_astream())

    def fingerprint(records):
        return sorted(
            (r.effect_type, r.business_key, r.attempt, r.status.value, r.branch_id)
            for r in records
        )

    assert fingerprint(stream_records) == fingerprint(astream_records)
