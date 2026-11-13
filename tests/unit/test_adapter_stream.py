"""流式适配器单元测试：假 graph stub 验证 astream/astream_events 的 run 生命周期。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agentreplayguard import RunInputKind, Scenario, UnsupportedGraphError
from agentreplayguard.adapters.langgraph import LangGraphAdapter


def _edge(source: str, conditional: bool = False) -> SimpleNamespace:
    return SimpleNamespace(source=source, target="next", conditional=conditional)


def _state(checkpoint_id: str | None = "cp-1") -> SimpleNamespace:
    return SimpleNamespace(
        config={"configurable": {"thread_id": "thread-0001", "checkpoint_id": checkpoint_id}}
    )


def _edges() -> SimpleNamespace:
    return SimpleNamespace(edges=[_edge("__start__"), _edge("refund"), _edge("notify")])


class StreamGraph:
    def __init__(self, *, checkpointer: bool = True, chunks=(), fail_on=None) -> None:
        self.checkpointer = object() if checkpointer else None
        self._chunks = list(chunks)
        self._fail_on = fail_on

    def invoke(self, input, config):
        return {"ok": True}

    async def ainvoke(self, input, config):
        return {"ok": True}

    def get_state(self, config):
        return _state()

    def get_graph(self):
        return _edges()

    async def astream(self, input, config, **kwargs):
        for chunk in self._chunks:
            if self._fail_on == "first":
                raise ValueError("boom")
            yield chunk

    async def astream_events(self, input, config, **kwargs):
        for event in self._chunks:
            yield event


class SyncOnlyGraph:
    def __init__(self) -> None:
        self.checkpointer = object()

    def invoke(self, input, config):
        return {"ok": True}

    def get_state(self, config):
        return _state()

    def get_graph(self):
        return _edges()


async def _drain(agen):
    result = []
    async for item in agen:
        result.append(item)
    return result


def test_astream_creates_start_segment():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(
        scenario, StreamGraph(chunks=[{"a": {"x": 1}}, {"b": {"x": 2}}])
    )

    chunks = asyncio.run(_drain(adapter.astream({"x": 0})))

    assert chunks == [{"a": {"x": 1}}, {"b": {"x": 2}}]
    report = scenario.finish()
    assert len(report.run_segments) == 1
    segment = report.run_segments[0]
    assert segment.input_kind is RunInputKind.START
    assert segment.run_id == "run-0001"
    assert segment.checkpoint_before == "cp-1"


def test_astream_effect_attributed_to_run():
    scenario = Scenario("s")

    class GraphWithGuard(StreamGraph):
        async def astream(self, input, config, **kwargs):
            scenario.guard().call("refund", lambda: None, key=lambda _: "R-1")
            yield {"a": {}}

    adapter = LangGraphAdapter(scenario, GraphWithGuard())
    asyncio.run(_drain(adapter.astream({})))

    record = scenario.effects.records[0]
    assert record.run_id == "run-0001"
    assert record.thread_id == "thread-0001"
    assert record.checkpoint_id == "cp-1"


def test_astream_missing_capability_rejected():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, SyncOnlyGraph())

    with pytest.raises(UnsupportedGraphError):
        asyncio.run(_drain(adapter.astream({})))

    assert scenario.finish().run_segments == ()


def test_astream_mid_exception_finishes_run_and_propagates():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, StreamGraph(chunks=[{}], fail_on="first"))

    with pytest.raises(ValueError):
        asyncio.run(_drain(adapter.astream({})))

    report = scenario.finish()
    assert len(report.run_segments) == 1
    assert report.run_segments[0].error_type == "ValueError"


def test_astream_early_break_finishes_run():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, StreamGraph(chunks=[{"a": {}}, {"b": {}}, {"c": {}}]))

    async def break_early():
        async for _chunk in adapter.astream({}):
            break

    asyncio.run(break_early())

    report = scenario.finish()
    assert len(report.run_segments) == 1
    assert report.run_segments[0].error_type is None


def test_astream_events_creates_segment():
    scenario = Scenario("s")
    events = [
        {"event": "on_chain_start"},
        {"event": "on_chain_stream"},
        {"event": "on_chain_end"},
    ]
    adapter = LangGraphAdapter(scenario, StreamGraph(chunks=events))

    got = asyncio.run(_drain(adapter.astream_events({}, version="v2")))

    assert got == events
    report = scenario.finish()
    assert len(report.run_segments) == 1
    assert report.run_segments[0].run_id == "run-0001"
