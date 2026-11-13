# Quickstart: 多框架工具副作用记账

**Feature**: 007-multi-framework-tools

## 核心用法：装饰工具函数

任何框架的工具函数都是普通 Python callable，用 `guard.effect()` 装饰即可记账：

```python
from agentreplayguard import NoDuplicateEffects, Scenario

scenario = Scenario("tools", seed=0, invariants=[NoDuplicateEffects("refund")])
guard = scenario.guard()

@guard.effect("refund", key="refund_id", idempotency_key="idempotency_key")
def refund(refund_id: str, amount_cents: int, idempotency_key: str | None = None) -> str:
    return f"refunded {refund_id}"

refund("R-1", 100)  # 自动记账
refund("R-1", 100)  # 重复 → NoDuplicateEffects 报违规
```

异步工具自动识别：

```python
@guard.effect("refund", key="refund_id")
async def refund_async(refund_id: str) -> str:
    return f"refunded {refund_id}"

await refund_async("R-2")
```

## OpenAI Agents SDK（可选）

```python
from agents import Agent, RunConfig, Runner
from agents.testing import ScriptedModel, assistant_message, function_call

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

## CrewAI / AutoGen

工具函数直接用 `guard.effect()` 装饰即可，无需 Agent/LLM：

```python
# CrewAI
@tool
@guard.effect("search", key="query")
def search(query: str) -> str: ...

# AutoGen 工具函数同理
@guard.effect("notify", key="user_id")
def notify(user_id: str) -> str: ...
```

## 验证

```bash
uv run pytest examples/multi_framework -q
uv run pytest -q
```
