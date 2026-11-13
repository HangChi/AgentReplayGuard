# 快速开始

AgentReplayGuard 面向 **LangGraph + pytest** 做副作用安全测试：用确定性的故障注入和
effect 账本，验证重试、Checkpoint 恢复与 Interrupt 重放不会重复执行支付、退款、
写入、通知等业务操作。

## 安装

```bash
uv sync --extra dev --extra langgraph --extra httpx --extra requests --extra agents
```

- 核心包仅依赖标准库；`langgraph`、`httpx`、`requests`、`openai-agents` 是可选适配层依赖。
- 运行测试不需要网络，也无需任何真实支付/退款/邮件服务。

## 最小示例

1. 用 `Scenario` 声明一个场景：注入「提交后响应丢失」故障，并挂上
   `NoDuplicateEffects` 不变量。

```python
from agentreplayguard import FaultKind, FaultPlan, FaultRule, NoDuplicateEffects, Scenario

scenario = Scenario(
    "refund-lost-ack",
    seed=7,
    faults=FaultPlan([
        FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1),
    ]),
    invariants=[NoDuplicateEffects("refund")],
)
```

2. 用 `scenario.guard().effect(...)` 包裹有副作用的工具，并声明业务键。

```python
@scenario.guard().effect("refund", key="refund_id")
def refund(refund_id: str, amount_cents: int) -> str:
    ...
```

3. 把工具放进 LangGraph 图，显式声明重试策略，用 `LangGraphAdapter` 驱动。

```python
from langgraph.graph import StateGraph
from langgraph.types import RetryPolicy
from agentreplayguard.adapters.langgraph import LangGraphAdapter

builder = StateGraph(dict)
builder.add_node(
    "refund",
    lambda state: refund(state["refund_id"], state["amount_cents"]),
    retry_policy=RetryPolicy(
        max_attempts=3,
        retry_on=(TimeoutError, ConnectionError),
        initial_interval=0,
        jitter=False,
    ),
)
builder.set_entry_point("refund")
builder.add_edge("refund", "__end__")

adapter = LangGraphAdapter(scenario, builder.compile())
adapter.invoke({"refund_id": "order-42", "amount_cents": 1000})
```

4. 结束场景，断言报告。

```python
report = scenario.finish()
assert not report.ok
print(report.format())
```

## 异步工具与异步图

`effect` 会自动识别 `async def` 工具，记账与故障注入语义和同步路径一致：

```python
@scenario.guard().effect("refund", key="refund_id")
async def refund(refund_id: str, amount_cents: int) -> str:
    ...

import asyncio

asyncio.run(refund("order-42", 1000))
```

动态调用时可使用 `await scenario.guard().acall("refund", refund, refund_id="order-42", key="refund_id")`。
异步图使用 `ainvoke` / `aresume` / `aresume_interrupt`：

```python
adapter = LangGraphAdapter(scenario, async_graph)
asyncio.run(adapter.ainvoke({"refund_id": "order-42", "amount_cents": 1000}))
asyncio.run(adapter.aresume())
```

注意：

- 同步 `guard.call(...)` 执行 `async def` 工具会立即抛 `ScenarioConfigError`，请改用
  `acall` 或直接 `await` 被装饰的工具。
- 直接调用异步工具但忘记 `await` 属于 Python 协程语义，工具无法拦截，请确保在异步
  上下文中等待。

## HTTP 客户端（httpx）

如果业务副作用经由真实的 `httpx.Client` / `httpx.AsyncClient` 发出，可以只替换 transport，
业务调用代码零改动。下例中的 `handler` 是进程内模拟服务的处理函数（可参考
`examples/refund/http_tools.py`）：

```python
import json

import httpx

from agentreplayguard import FaultKind, FaultPlan, FaultRule, NoDuplicateEffects, Scenario
from agentreplayguard.adapters.httpx import FaultyTransport, HttpEffect

scenario = Scenario(
    "http-refund-lost-ack",
    seed=7,
    faults=FaultPlan([
        FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1),
    ]),
    invariants=[NoDuplicateEffects("refund")],
)


def classify(request: httpx.Request) -> HttpEffect | None:
    if request.method != "POST" or request.url.path != "/refunds":
        return None  # 只读或无关请求直接透传，不记账
    body = json.loads(request.content)
    return HttpEffect(
        effect_type="refund",
        business_key=body["refund_id"],
        params={"amount_cents": body["amount_cents"]},
        idempotency_key=request.headers.get("Idempotency-Key"),
    )


transport = FaultyTransport(httpx.MockTransport(handler), scenario, classify)
with httpx.Client(transport=transport) as client:
    client.post("https://sim.test/refunds", json={"refund_id": "order-42", "amount_cents": 1000})
```

异步客户端使用 `AsyncFaultyTransport`，语义与同步版一致：

```python
from agentreplayguard.adapters.httpx import AsyncFaultyTransport

transport = AsyncFaultyTransport(httpx.MockTransport(handler), scenario, classify)
async with httpx.AsyncClient(transport=transport) as client:
    await client.post("https://sim.test/refunds", json={"refund_id": "order-42", "amount_cents": 1000})
```

注意：

- `httpx` 是可选依赖：`pip install agentreplayguard[httpx]`；未安装时核心包仍可正常导入。
- 注入故障会表现为 httpx 标准异常：提交前为 `ConnectTimeout` / `ConnectError`，
  提交后为 `ReadTimeout` / `ReadError`，`server_error` 为 `HTTPStatusError`。
- 提交边界是底层 transport 返回响应（响应头到达）；流式响应体读取失败不在 lost-ack 语义内。
- 示例见 `examples/refund/http_tools.py` 与 `examples/refund/test_refund_http.py`。

## HTTP 客户端（requests）

如果业务副作用经由 `requests` 发出，用 `RequestsAdapter` 挂载到 Session，语义与 httpx 版
一致：

```python
import requests
from agentreplayguard.adapters.requests import RequestsAdapter, HttpEffect

def classify(request: requests.PreparedRequest) -> HttpEffect | None:
    if request.method != "POST":
        return None
    body = json.loads(request.body or b"{}")
    return HttpEffect(
        effect_type="refund",
        business_key=body["refund_id"],
        params={"amount_cents": body["amount_cents"]},
        idempotency_key=request.headers.get("Idempotency-Key"),
    )

adapter = RequestsAdapter(base_adapter, scenario, classify)
session = requests.Session()
session.mount("https://", adapter)
session.post("https://sim.test/refunds", json={"refund_id": "order-42", "amount_cents": 1000})
```

注意：

- `requests` 是可选依赖：`pip install agentreplayguard[requests]`。
- 注入故障映射为 requests 标准异常：`ConnectTimeout` / `ReadTimeout` / `ConnectionError` /
  `HTTPError`（500）/ `ChunkedEncodingError`。
- 示例见 `examples/refund/test_refund_requests.py`。

## 并行图（fan-out）与并发提交

并行分支是重复副作用的独立来源：fan-out 图里多个分支若各自提交同一业务键，会产生重复。
`LangGraphAdapter` 现在支持并行图，并为每个 effect 记录其来源节点（`branch_id`）：

```python
import operator
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from agentreplayguard import NoDuplicateEffects, Scenario
from agentreplayguard.adapters.langgraph import LangGraphAdapter


class State(TypedDict):
    log: Annotated[list[str], operator.add]


scenario = Scenario("parallel-refund", seed=0, invariants=[NoDuplicateEffects("refund")])
guard = scenario.guard()


def build_graph():
    g = StateGraph(State)

    def refund_a(s):
        guard.call("refund", lambda: None, key=lambda _: "ORDER-1")
        return {"log": ["refund_a"]}

    def refund_b(s):
        guard.call("refund", lambda: None, key=lambda _: "ORDER-1")
        return {"log": ["refund_b"]}

    g.add_node("refund_a", refund_a)
    g.add_node("refund_b", refund_b)
    g.add_edge(START, "refund_a")
    g.add_edge(START, "refund_b")  # fan-out
    g.add_edge("refund_a", END)
    g.add_edge("refund_b", END)
    return g.compile()


adapter = LangGraphAdapter(scenario, build_graph())
adapter.invoke({"log": []})
report = scenario.finish()
assert not report.ok  # ORDER-1 被两个分支各提交一次
```

异步交错 / 手动并发提交可用 `ConcurrentCommitDetected` 判定「并发」重复：

```python
import asyncio
from agentreplayguard import ConcurrentCommitDetected

scenario = Scenario("cc", seed=0, invariants=[ConcurrentCommitDetected("refund")])
guard = scenario.guard()

async def refund():
    await asyncio.sleep(0.01)
    return "ok"

async def run():
    await asyncio.gather(
        guard.acall("refund", refund, key=lambda a: "ORDER-1"),
        guard.acall("refund", refund, key=lambda a: "ORDER-1"),
    )

asyncio.run(run())
assert not scenario.finish().ok
```

注意：

- 并行分支写同一 channel 必须用 `Annotated` + reducer，否则 LangGraph 抛
  `InvalidUpdateError`（图设计问题，工具不介入）。
- LangGraph 的同步 fan-out 是线程池真并发，effect 的追加顺序（`sequence`）不保证确定；
  但**检测结论与分支归属（`branch_id`）是确定的**。
- 示例见 `examples/refund/graph_parallel.py` 与 `examples/refund/test_refund_parallel.py`。

## 流式接口（astream / astream_events）

用流式方式驱动图时，`LangGraphAdapter` 提供 `astream` / `astream_events`，effect 的归属
（run/thread/checkpoint/branch）与 `ainvoke` 一致：

```python
import asyncio
from agentreplayguard import Scenario
from agentreplayguard.adapters.langgraph import LangGraphAdapter

scenario = Scenario("stream", seed=0)
adapter = LangGraphAdapter(scenario, graph)


async def main():
    async for chunk in adapter.astream({"input": ...}):
        print(chunk)
    # 或消费事件流
    async for event in adapter.astream_events({"input": ...}, version="v2"):
        print(event["event"])


asyncio.run(main())
report = scenario.finish()  # effect 归属与 ainvoke 一致
```

注意：

- `astream` / `astream_events` 都是异步生成器，必须 `async for` 遍历。
- 故障注入、重试、`NoDuplicateEffects` / `ConcurrentCommitDetected` 检测在流式下与
  `ainvoke` 完全等价。
- 提前 `break` 退出遍历会正常收尾 run，不产生脏状态。
- 示例见 `examples/refund/test_refund_streaming.py`。

## 其他 Agent 框架（工具函数级接入）

OpenAI Agents SDK、CrewAI、AutoGen 的工具函数**本质都是普通 Python callable**，用
`guard.effect()` 装饰即可复用全部能力，无需驱动整图/整 agent：

```python
from agentreplayguard import NoDuplicateEffects, Scenario

scenario = Scenario("tools", seed=0, invariants=[NoDuplicateEffects("refund")])
guard = scenario.guard()

@guard.effect("refund", key="refund_id")
def refund(refund_id: str) -> str:
    return f"refunded {refund_id}"
```

OpenAI Agents SDK 用官方 `ScriptedModel` 离线跑工具管线（`@function_tool` 在外、
`@guard.effect` 在内）：

```python
from agents import Agent, RunConfig, Runner, function_tool
from agents.testing import ScriptedModel, assistant_message, function_call

@function_tool
@guard.effect("lookup", key="order_id")
def lookup_order(order_id: str) -> str:
    return f"order {order_id}"

model = ScriptedModel([
    [function_call("lookup_order", '{"order_id": "ORD-1"}', call_id="c1")],
    [assistant_message("delivered")],
])
agent = Agent(name="billing", tools=[lookup_order], model=model)
result = await Runner.run(agent, "...", run_config=RunConfig(tracing_disabled=True))
```

注意：

- `openai-agents` 是可选依赖：`pip install 'agentreplayguard[agents]'`。
- 核心测试必须离线（ScriptedModel 不发真实 LLM 请求），保证确定性；真实 LLM 只用于
  手动演示（`examples/multi_framework/demo_real_llm.py`，环境变量注入端点与密钥）。
- 完整接入说明见 `examples/multi_framework/README.md`。

## pytest fixture

安装后插件自动注册 `replayguard` fixture，等价于 `Scenario` 构造器：

```python
def test_something(replayguard):
    scenario = replayguard("my-scenario", seed=0)
```

## 报告导出（结构化）

`ScenarioReport` 提供 `to_dict()` / `to_json()`，把报告导出为纯 JSON 可序列化的结构化数据
（Enum 转 value 字符串），供 CI 存档、审计、跨工具消费：

```python
report = scenario.finish()
data = report.to_dict()   # {"scenario_name": ..., "effects": [...], "violations": [...]}
json_str = report.to_json()  # 确定性 JSON（同 seed 逐字节一致）

import json
json.loads(json_str)["violations"]  # 结构化消费违规信息
```

导出与 `format()` 信息内容一致，确定性（字段顺序固定、无 wall clock）。

## 可运行示例

`examples/refund/` 包含完整示例（lost-ack、幂等键、Checkpoint 恢复、Interrupt 重放、
并行 fan-out、流式）：

```bash
uv run pytest examples/refund -q
```

## 更多

- 公开 API 契约：[contracts/public-api.md](../specs/001-effect-safety-testing/contracts/public-api.md)
- 完整端到端验收步骤：[specs/quickstart.md](../specs/001-effect-safety-testing/quickstart.md)
- HTTP 传输层契约：[http-transport-api.md](../specs/003-http-fault-transport/contracts/http-transport-api.md)
- HTTP 传输层验收：[quickstart.md](../specs/003-http-fault-transport/quickstart.md)
- 并行图分支归属契约：[branch-attribution.md](../specs/004-concurrent-parallel-graph/contracts/branch-attribution.md)
- 流式入口契约：[streaming-entry.md](../specs/005-streaming-fault-injection/contracts/streaming-entry.md)
- requests 适配器契约：[requests-adapter.md](../specs/006-requests-adapter/contracts/requests-adapter.md)
- 多框架工具接入契约：[tool-guard.md](../specs/007-multi-framework-tools/contracts/tool-guard.md)
