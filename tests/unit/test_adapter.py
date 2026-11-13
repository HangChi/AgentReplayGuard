"""LangGraphAdapter 单元测试：用假 graph stub 验证 checkpoint 读取与 RunSegment 归属。"""

from __future__ import annotations

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


def make_graph(
    *,
    checkpointer: bool = True,
    fanout: bool = False,
    on_invoke=None,
    checkpoint_id: str | None = "cp-1",
):
    class State:
        def __init__(self) -> None:
            self.config = {
                "configurable": {"thread_id": "thread-0001", "checkpoint_id": checkpoint_id}
            }

    class Graph:
        def __init__(self) -> None:
            self.checkpointer = object() if checkpointer else None

        def invoke(self, input, config):
            if on_invoke is not None:
                return on_invoke(input, config)
            return {"ok": True}

        def get_state(self, config):
            return State()

        def get_graph(self):
            edges = [_edge("__start__"), _edge("refund"), _edge("notify")]
            if fanout:
                edges.append(_edge("refund"))
            return SimpleNamespace(edges=edges)

    return Graph()


def test_missing_graph_api_rejected():
    scenario = Scenario("s")
    graph = SimpleNamespace(invoke=lambda *a, **k: {})
    with pytest.raises(UnsupportedGraphError):
        LangGraphAdapter(scenario, graph)


def test_invoke_creates_start_segment():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, make_graph())

    run = adapter.invoke({"refund_id": "R-1"})

    assert run.segment.input_kind is RunInputKind.START
    assert run.segment.run_id == "run-0001"
    assert run.segment.thread_id == "thread-0001"
    assert run.segment.checkpoint_before == "cp-1"
    assert run.output == {"ok": True}
    assert run.interrupts == ()


def test_resume_requires_prior_run():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, make_graph())
    with pytest.raises(ScenarioConfigError):
        adapter.resume()


def test_resume_without_checkpointer_raises():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, make_graph(checkpointer=False))
    adapter.invoke()
    with pytest.raises(UnsupportedGraphError):
        adapter.resume()


def test_resume_creates_resume_segment():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, make_graph())
    adapter.invoke()

    run = adapter.resume()

    assert run.segment.input_kind is RunInputKind.RESUME
    assert run.segment.run_id == "run-0002"
    assert len(scenario.finish().run_segments) == 2


def test_effect_attributed_to_run():
    scenario = Scenario("s")

    def on_invoke(input, config):
        scenario.guard().call(
            "refund",
            lambda refund_id: refund_id,
            refund_id="R-1",
            key="refund_id",
        )
        return {"ok": True}

    adapter = LangGraphAdapter(scenario, make_graph(on_invoke=on_invoke))
    adapter.invoke()

    record = scenario.effects.records[0]
    assert record.run_id == "run-0001"
    assert record.thread_id == "thread-0001"
    assert record.checkpoint_id == "cp-1"


def test_strict_graph_accepts_fanout():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, make_graph(fanout=True))
    adapter.invoke()  # 不再拒绝 fan-out


def test_non_strict_skips_fanout_and_warns():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, make_graph(fanout=True), strict_graph=False)
    adapter.invoke()

    report = scenario.finish()
    assert any("strict_graph" in warning for warning in report.warnings)
