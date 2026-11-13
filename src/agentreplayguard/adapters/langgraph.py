"""LangGraphAdapter：驱动串行图，按 RunSegment 归属 effect。

仅使用 LangGraph 公共 API（invoke/ainvoke、get_state、get_graph），不包裹用户节点。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from langgraph.types import Command

from ..errors import ScenarioConfigError, UnsupportedGraphError
from ..report import GraphRun, RunInputKind, RunSegment
from ..scenario import Scenario

_GRAPH_METHODS = ("invoke", "get_state", "get_graph")


class LangGraphAdapter:
    """在 Scenario 之上驱动一个已编译的 LangGraph 串行图。"""

    def __init__(
        self,
        scenario: Scenario,
        graph: Any,
        *,
        thread_id: str | None = None,
        strict_graph: bool = True,
    ) -> None:
        self._scenario = scenario
        self._graph = graph
        self._thread_id = thread_id or "thread-0001"
        self._strict_graph = strict_graph
        self._last_segment: RunSegment | None = None

        self._validate_graph()

    @property
    def thread_id(self) -> str:
        return self._thread_id

    def invoke(self, input: Mapping[str, Any] | None = None) -> GraphRun:
        return self._run(RunInputKind.START, input)

    def resume(self, input: Mapping[str, Any] | None = None) -> GraphRun:
        if self._last_segment is None:
            raise ScenarioConfigError("resume requires a prior run")
        self._check_checkpointer()
        return self._run(RunInputKind.RESUME, input)

    def resume_interrupt(self, value: Any = None) -> GraphRun:
        if self._last_segment is None or not self._last_segment.interrupted:
            raise ScenarioConfigError(
                "resume_interrupt requires a prior interrupted run"
            )
        self._check_checkpointer()
        return self._run(RunInputKind.INTERRUPT_RESUME, Command(resume=value))

    async def ainvoke(self, input: Mapping[str, Any] | None = None) -> GraphRun:
        return await self._arun(RunInputKind.START, input)

    async def aresume(self, input: Mapping[str, Any] | None = None) -> GraphRun:
        if self._last_segment is None:
            raise ScenarioConfigError("aresume requires a prior run")
        self._check_checkpointer()
        return await self._arun(RunInputKind.RESUME, input)

    async def aresume_interrupt(self, value: Any = None) -> GraphRun:
        if self._last_segment is None or not self._last_segment.interrupted:
            raise ScenarioConfigError(
                "aresume_interrupt requires a prior interrupted run"
            )
        self._check_checkpointer()
        return await self._arun(RunInputKind.INTERRUPT_RESUME, Command(resume=value))

    def state(self) -> Any:
        return self._graph.get_state(self._config())

    # 内部实现

    def _config(self) -> dict[str, Any]:
        return {"configurable": {"thread_id": self._thread_id}}

    def _validate_graph(self) -> None:
        for method in _GRAPH_METHODS:
            if not callable(getattr(self._graph, method, None)):
                raise UnsupportedGraphError(f"graph is missing {method}()")
        fanout = self._find_fanout()
        if not fanout:
            return
        if self._strict_graph:
            raise UnsupportedGraphError(
                f"node {fanout[0]!r} has multiple unconditional outgoing edges; "
                "parallel fan-out is not supported"
            )
        self._scenario._warn("strict_graph=False; parallel fan-out check skipped")

    def _ensure_async_capable(self) -> None:
        if not callable(getattr(self._graph, "ainvoke", None)):
            raise UnsupportedGraphError("graph is missing ainvoke()")

    def _find_fanout(self) -> list[str]:
        outgoing: dict[str, int] = {}
        for edge in self._graph.get_graph().edges:
            if not edge.conditional:
                source = edge.source
                outgoing[source] = outgoing.get(source, 0) + 1
        return [source for source, count in outgoing.items() if count > 1]

    def _check_checkpointer(self) -> None:
        if getattr(self._graph, "checkpointer", None) is None:
            raise UnsupportedGraphError(
                "graph has no checkpointer; resume requires one"
            )

    def _checkpoint_id(self) -> str | None:
        if getattr(self._graph, "checkpointer", None) is None:
            return None
        state = self._graph.get_state(self._config())
        configurable: Any = state.config.get("configurable", {})
        return cast("str | None", configurable.get("checkpoint_id"))

    def _run(
        self,
        input_kind: RunInputKind,
        input: Any,
    ) -> GraphRun:
        checkpoint_before = self._checkpoint_id()
        run_id = self._scenario._begin_run(self._thread_id, checkpoint_before)
        started_tick = self._scenario._tick()

        output: Mapping[str, Any] | None = None
        interrupts: tuple[Any, ...] = ()
        exc: Exception | None = None

        try:
            output = self._graph.invoke(input, self._config())
        except Exception as caught:
            exc = caught
        else:
            interrupts = self._extract_interrupts(output)

        run = self._finish_run(
            run_id=run_id,
            input_kind=input_kind,
            checkpoint_before=checkpoint_before,
            started_tick=started_tick,
            output=output,
            interrupts=interrupts,
            exc=exc,
        )
        if exc is not None:
            raise exc
        return run

    async def _arun(
        self,
        input_kind: RunInputKind,
        input: Any,
    ) -> GraphRun:
        self._ensure_async_capable()
        checkpoint_before = self._checkpoint_id()
        run_id = self._scenario._begin_run(self._thread_id, checkpoint_before)
        started_tick = self._scenario._tick()

        output: Mapping[str, Any] | None = None
        interrupts: tuple[Any, ...] = ()
        exc: BaseException | None = None

        try:
            output = await self._graph.ainvoke(input, self._config())
        except BaseException as caught:
            exc = caught
        else:
            interrupts = self._extract_interrupts(output)

        run = self._finish_run(
            run_id=run_id,
            input_kind=input_kind,
            checkpoint_before=checkpoint_before,
            started_tick=started_tick,
            output=output,
            interrupts=interrupts,
            exc=exc,
        )
        if exc is not None:
            raise exc
        return run

    def _finish_run(
        self,
        *,
        run_id: str,
        input_kind: RunInputKind,
        checkpoint_before: str | None,
        started_tick: int,
        output: Mapping[str, Any] | None,
        interrupts: tuple[Any, ...],
        exc: BaseException | None,
    ) -> GraphRun:
        checkpoint_after = self._checkpoint_id()
        segment = RunSegment(
            run_id=run_id,
            thread_id=self._thread_id,
            input_kind=input_kind,
            checkpoint_before=checkpoint_before,
            checkpoint_after=checkpoint_after,
            started_tick=started_tick,
            ended_tick=self._scenario._tick(),
            interrupted=bool(interrupts),
            error_type=type(exc).__name__ if exc is not None else None,
            error_message=str(exc) if exc is not None else None,
        )
        self._scenario._add_run_segment(segment)
        self._scenario._end_run()
        self._last_segment = segment
        return GraphRun(segment=segment, output=output, interrupts=interrupts)

    @staticmethod
    def _extract_interrupts(output: Mapping[str, Any] | None) -> tuple[Any, ...]:
        if isinstance(output, dict) and "__interrupt__" in output:
            value = output["__interrupt__"]
            if value is None:
                return ()
            return tuple(value)
        return ()
