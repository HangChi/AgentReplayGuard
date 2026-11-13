# 多框架工具副作用记账

本目录演示「用 `guard.effect()` 装饰工具函数」即可把 AgentReplayGuard 接入任意 Agent 框架的
副作用检测。核心原理：这些框架的工具函数**本质都是普通 Python callable**，副作用发生在
「函数被调用的那一刻」，与本工具 `guard.effect()` 的拦截点完全一致。

## 通用用法

```python
from agentreplayguard import NoDuplicateEffects, Scenario

scenario = Scenario("tools", seed=0, invariants=[NoDuplicateEffects("refund")])
guard = scenario.guard()

@guard.effect("refund", key="refund_id")
def refund(refund_id: str) -> str:
    return f"refunded {refund_id}"
```

## OpenAI Agents SDK

用官方 `ScriptedModel` 离线跑工具管线，`@function_tool` 在外、`@guard.effect` 在内：

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

完整可运行示例见 `test_openai_agents_sdk.py`（依赖 `openai-agents`，未安装时自动跳过）。

## CrewAI

CrewAI 工具可直接调用其 `run()` 接口（无需 Agent/LLM），用 `guard.effect()` 装饰即可：

```python
from crewai.tools import tool

@tool
@guard.effect("search", key="query")
def search(query: str) -> str:
    return f"results for {query}"

# 直接调用（离线，不经过 Agent/LLM）
search.run(query="hello")
```

> 注意：`@tool` 在外、`@guard.effect` 在内，保证 CrewAI 能读到原始签名生成工具 schema。
> Agent 级执行需 mock LLM（CrewAI 0.30+ 用 `llm=` 参数注入 mock），不在本示例范围。

## AutoGen

AutoGen 工具函数同理是普通 callable，直接装饰：

```python
@guard.effect("notify", key="user_id")
def notify(user_id: str) -> str:
    return f"notified {user_id}"
```

> AutoGen 无官方离线 scripted 测试设施，Agent 级执行需自建 mock，本示例仅覆盖工具函数级。
