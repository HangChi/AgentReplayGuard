# Quickstart Validation: 异步副作用安全测试

**Date**: 2026-11-13 | **Spec**: [spec.md](./spec.md) | **Contracts**: [public-api-additions.md](./contracts/public-api-additions.md)

本指南用于验收 002 异步能力，不替代 001 的快速开始。

## 前置条件

```bash
uv sync --extra dev --extra langgraph
```

## 1. 回归同步能力（必须不退化）

```bash
uv run pytest tests examples/refund -q
uv run ruff check .
uv run mypy src/agentreplayguard
```

预期：全部通过，ruff 与 mypy 无错误。

## 2. 验收异步记账

```bash
uv run pytest tests/unit/test_guard_async.py tests/unit/test_adapter_async.py -q
```

预期覆盖：

- 正常异步提交 → 1 条 `committed`
- 异步 lost-ack 重试 → 2 条 `committed`，attempt 为 1、2
- 提交前故障 → `not_committed` 且函数未执行
- 业务异常 → `not_committed` 且异常原样传播
- 取消 → `unknown` 且传播 `CancelledError`
- 同步入口传入异步函数 → `ScenarioConfigError` 且账本零新增

## 3. 验收异步图驱动

```bash
uv run pytest tests/integration/test_langgraph_async.py -q
```

预期覆盖：

- `ainvoke` 首次执行并记录 run 片段
- `aresume` 从 checkpoint 恢复，已完成副作用不重复
- `aresume_interrupt` 区分 interrupt 前/后的重复结论
- 同步与异步等价场景的 effect 数量、状态序列、attempt 一致

## 4. 运行异步示例

```bash
uv run pytest examples/refund/test_refund_async.py -q
```

预期：异步 lost-ack 场景检测到 2 条已提交退款并使不变量失败；幂等键场景通过。

## 5. 手工最小验证

```python
import asyncio

from agentreplayguard import FaultKind, FaultPlan, FaultRule, NoDuplicateEffects, Scenario

scenario = Scenario(
    "async-refund-lost-ack",
    seed=7,
    faults=FaultPlan([
        FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1),
    ]),
    invariants=[NoDuplicateEffects("refund")],
)

@scenario.guard().effect("refund", key="refund_id")
async def refund(refund_id: str, amount_cents: int) -> str:
    return "ok"

async def main() -> None:
    for _ in range(2):
        try:
            await refund("order-42", 1000)
        except Exception:
            pass
    report = scenario.finish()
    assert not report.ok
    print(report.format())

asyncio.run(main())
```

预期：报告显示同一业务键 2 条 `committed`，不变量失败。

## 6. 常见错误

- 用同步 `guard.call(...)` 执行 `async def` 工具：立即抛 `ScenarioConfigError`，这是预期
  行为，请改用 `await guard.acall(...)` 或直接 await 被装饰的异步工具。
- 调用被装饰的异步工具但忘记 `await`：Python 只会在协程被回收时告警，工具无法拦截；
  请确保在异步上下文中 await。
- 在未安装 `langgraph` extra 的环境中导入适配器：会得到 `ImportError`，核心包与同步/异步
  guard 不受影响。

## 7. 覆盖率

```bash
uv run coverage run -m pytest tests examples/refund
uv run coverage report --fail-under=90
```

预期：总覆盖率 ≥90%，异步新增模块纳入统计。
