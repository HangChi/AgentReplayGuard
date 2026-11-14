# Quickstart: 并发与并行图的副作用竞态检测

**Feature**: 004-concurrent-parallel-graph

## 场景：并行分支重复退款

一个下单后的 fan-out 图，两个并行分支各自尝试退款同一订单，无幂等键时应被检测为重复。

```python
import operator
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END

from agentreplayguard import Scenario
from agentreplayguard.invariants import NoDuplicateEffects
from agentreplayguard.adapters.langgraph import LangGraphAdapter


class State(TypedDict):
    log: Annotated[list[str], operator.add]  # reducer 保证并行写合法


def make_graph(scenario: Scenario):
    guard = scenario.guard()

    def notify(s):
        # 分支 notify：退款订单 ORDER-1
        guard.call("refund", lambda: None, key=lambda _: "ORDER-1")
        return {"log": ["notify"]}

    def deduct(s):
        # 分支 deduct：也退款订单 ORDER-1（缺陷：应只退一次）
        guard.call("refund", lambda: None, key=lambda _: "ORDER-1")
        return {"log": ["deduct"]}

    def start(s):
        return {"log": ["start"]}

    g = StateGraph(State)
    g.add_node("start", start)
    g.add_node("notify", notify)
    g.add_node("deduct", deduct)
    g.add_edge(START, "start")
    g.add_edge("start", "notify")
    g.add_edge("start", "deduct")  # fan-out
    g.add_edge("notify", END)
    g.add_edge("deduct", END)
    return g.compile()


scenario = Scenario("parallel-duplicate-refund", seed=0, invariants=[NoDuplicateEffects("refund")])
adapter = LangGraphAdapter(scenario, make_graph(scenario))
adapter.invoke({"log": []})

report = scenario.finish()
print(report.format())
assert not report.ok  # 检测到 ORDER-1 被并行提交两次
```

## 验证步骤

```bash
# 全量测试（含新增 fan-out / 并发用例）
uv run pytest -q

# 静态检查
uv run ruff check .
uv run mypy src/agentreplayguard

# 覆盖率（核心模块 ≥90%）
uv run coverage run -m pytest -q && uv run coverage report --fail-under=90

# 确定性回归：同图结构连跑 20 次，检测结论与分支归属一致
uv run pytest tests/integration/test_parallel_graph.py -k deterministic -q
```

## 报告长什么样（预期）

并行重复场景下，`NoDuplicateEffects` 报违规，effect 行带 `branch_id`（节点名）定位分支来源：

```
duplicate_effects: refund ORDER-1 committed 2 times
  effect eff-000001  branch=notify
  effect eff-000002  branch=deduct
```

> 注意：并行分支的 effect 追加顺序（`sequence`）因真并发可能抖动，`eff-000001` 到底属于
> notify 还是 deduct 不保证，但「两条记录 branch 分别为 notify/deduct」是确定的。

## 注意

- 并行分支写同一 channel 必须用 `Annotated` + reducer，否则 LangGraph 抛
  `InvalidUpdateError`（这是图设计问题，工具不介入）。
- 同步 fan-out 是 LangGraph 线程池真并发，effect 追加顺序不保证确定；但检测结论与分支
  归属确定。多进程并发不在支持范围。
