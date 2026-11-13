# Quickstart: 流式接口的副作用归属与故障注入

**Feature**: 005-streaming-fault-injection

## 场景：用 astream 流式驱动图，effect 归属正确

```python
import asyncio
import operator
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END

from agentreplayguard import Scenario
from agentreplayguard.adapters.langgraph import LangGraphAdapter


class State(TypedDict):
    log: Annotated[list[str], operator.add]


def make_graph(scenario: Scenario):
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


scenario = Scenario("stream-demo", seed=0)
adapter = LangGraphAdapter(scenario, make_graph(scenario))


async def main():
    async for chunk in adapter.astream({"log": []}):
        print(chunk)  # {'a': {'log': ['a']}} → {'b': {'log': ['b']}}


asyncio.run(main())

report = scenario.finish()
for r in scenario.effects.records:
    # run_id 非空、branch_id 为产生节点名
    assert r.run_id == "run-0001"
    assert r.branch_id in ("a", "b")
print(report.format())
```

## astream_events 事件流

```python
async def main():
    async for event in adapter.astream_events({"log": []}, version="v2"):
        print(event["event"])  # on_chain_start / on_chain_stream / on_chain_end


asyncio.run(main())
scenario.finish()
```

## 验证步骤

```bash
uv run pytest tests/integration/test_streaming.py -q
uv run pytest -q
uv run ruff check .
uv run mypy src/agentreplayguard
uv run coverage run -m pytest -q && uv run coverage report --fail-under=90
```

## 注意

- `astream`/`astream_events` 都是异步生成器，必须 `async for` 遍历。
- 提前 `break` 退出遍历会正常收尾 run，不产生脏状态。
- 流式下故障注入、重试、`NoDuplicateEffects` 检测与 `ainvoke` 等价。
