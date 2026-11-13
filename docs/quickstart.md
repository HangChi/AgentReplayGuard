# 快速开始

AgentReplayGuard 面向 **LangGraph + pytest** 做副作用安全测试：用确定性的故障注入和
effect 账本，验证重试、Checkpoint 恢复与 Interrupt 重放不会重复执行支付、退款、
写入、通知等业务操作。

## 安装

```bash
uv sync --extra dev --extra langgraph --extra httpx
```

- 核心包仅依赖标准库；`langgraph` 与 `httpx` 是可选适配层依赖。
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

## pytest fixture

安装后插件自动注册 `replayguard` fixture，等价于 `Scenario` 构造器：

```python
def test_something(replayguard):
    scenario = replayguard("my-scenario", seed=0)
```

## 可运行示例

`examples/refund/` 包含完整示例（lost-ack、幂等键、Checkpoint 恢复、Interrupt 重放）：

```bash
uv run pytest examples/refund -q
```

## 更多

- 公开 API 契约：[contracts/public-api.md](../specs/001-effect-safety-testing/contracts/public-api.md)
- 完整端到端验收步骤：[specs/quickstart.md](../specs/001-effect-safety-testing/quickstart.md)
- HTTP 传输层契约：[http-transport-api.md](../specs/003-http-fault-transport/contracts/http-transport-api.md)
- HTTP 传输层验收：[quickstart.md](../specs/003-http-fault-transport/quickstart.md)
