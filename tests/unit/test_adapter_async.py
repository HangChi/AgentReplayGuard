"""异步适配器单元测试：假 graph stub 验证 ainvoke/aresume 的前置条件与 run 归属。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agentreplayguard import (
    RunInputKind,
    Scenario,
    ScenarioConfigError,
    UnsupportedGraphError,
)
from agentreplayguard.adapters.langgraph import LangGraphAdapter


def _edge(source: str, conditional: bool = False) -> SimpleNamespace:
    return SimpleNamespace(source=source, target="next", conditional=conditional)


def _state(checkpoint_id: str | None = "cp-1") -> SimpleNamespace:
    return SimpleNamespace(
        config={"configurable": {"thread_id": "thread-0001", "checkpoint_id": checkpoint_id}}
    )


def _edges() -> SimpleNamespace:
    return SimpleNamespace(edges=[_edge("__start__"), _edge("refund"), _edge("notify")])


class AsyncGraph:
    def __init__(self, *, checkpointer: bool = True, on_ainvoke=None) -> None:
        self.checkpointer = object() if checkpointer else None
        self._on_ainvoke = on_ainvoke

    def invoke(self, input, config):
        return {"ok": True}

    async def ainvoke(self, input, config):
        if self._on_ainvoke is not None:
            return await self._on_ainvoke(input, config)
        return {"ok": True}

    def get_state(self, config):
        return _state()

    def get_graph(self):
        return _edges()


class SyncOnlyGraph:
    def __init__(self) -> None:
        self.checkpointer = object()

    def invoke(self, input, config):
        return {"ok": True}

    def get_state(self, config):
        return _state()

    def get_graph(self):
        return _edges()


def test_ainvoke_creates_start_segment():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, AsyncGraph())

    run = asyncio.run(adapter.ainvoke({"refund_id": "R-1"}))

    assert run.segment.input_kind is RunInputKind.START
    assert run.segment.run_id == "run-0001"
    assert run.segment.checkpoint_before == "cp-1"
    assert run.output == {"ok": True}


def test_ainvoke_missing_capability_rejected():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, SyncOnlyGraph())

    with pytest.raises(UnsupportedGraphError):
        asyncio.run(adapter.ainvoke())

    assert scenario.finish().run_segments == ()


def test_aresume_requires_prior_run():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, AsyncGraph())

    with pytest.raises(ScenarioConfigError):
        asyncio.run(adapter.aresume())


def test_aresume_without_checkpointer_raises():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, AsyncGraph(checkpointer=False))
    asyncio.run(adapter.ainvoke())

    with pytest.raises(UnsupportedGraphError):
        asyncio.run(adapter.aresume())


def test_aresume_creates_resume_segment():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, AsyncGraph())
    asyncio.run(adapter.ainvoke())

    run = asyncio.run(adapter.aresume())

    assert run.segment.input_kind is RunInputKind.RESUME
    assert run.segment.run_id == "run-0002"
    assert len(scenario.finish().run_segments) == 2


def test_aresume_interrupt_requires_interrupted_run():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, AsyncGraph())
    asyncio.run(adapter.ainvoke())

    with pytest.raises(ScenarioConfigError):
        asyncio.run(adapter.aresume_interrupt({"approved": True}))


def test_async_effect_attributed_to_run():
    scenario = Scenario("s")

    async def on_ainvoke(input, config):
        await scenario.guard().acall(
            "refund",
            lambda refund_id: refund_id,
            refund_id="R-1",
            key="refund_id",
        )
        return {"ok": True}

    adapter = LangGraphAdapter(scenario, AsyncGraph(on_ainvoke=on_ainvoke))
    asyncio.run(adapter.ainvoke())

    record = scenario.effects.records[0]
    assert record.run_id == "run-0001"
    assert record.thread_id == "thread-0001"
    assert record.checkpoint_id == "cp-1"
