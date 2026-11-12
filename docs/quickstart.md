# 快速开始

AgentReplayGuard 面向 **LangGraph + pytest** 做副作用安全测试：用确定性的故障注入和
effect 账本，验证重试、Checkpoint 恢复与 Interrupt 重放不会重复执行支付、退款、
写入、通知等业务操作。

## 安装

```bash
pip install -e ".[dev,langgraph]"
```

- 核心包仅依赖标准库；`langgraph` 是可选适配层依赖。
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

## pytest fixture

安装后插件自动注册 `replayguard` fixture，等价于 `Scenario` 构造器：

```python
def test_something(replayguard):
    scenario = replayguard("my-scenario", seed=0)
```

## 可运行示例

`examples/refund/` 包含完整示例（lost-ack、幂等键、Checkpoint 恢复、Interrupt 重放）：

```bash
pytest examples/refund -q
```

## 更多

- 公开 API 契约：[contracts/public-api.md](../specs/001-effect-safety-testing/contracts/public-api.md)
- 完整端到端验收步骤：[specs/quickstart.md](../specs/001-effect-safety-testing/quickstart.md)
