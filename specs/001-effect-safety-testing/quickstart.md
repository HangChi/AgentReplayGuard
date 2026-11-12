# Quickstart Validation Guide

**Feature**: `001-effect-safety-testing`
**Date**: 2026-11-12
**Purpose**: 在实现完成后，用最少步骤验证 MVP 端到端可用，并作为发布前的验收脚本。

## 前置条件

- Python 3.10–3.13
- 可创建虚拟环境
- 首次安装依赖时需要网络；运行测试时不需要网络
- 不需要任何真实支付/退款/邮件服务

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,langgraph]"
```

## 运行全部示例

```bash
pytest examples/refund -q
```

**预期**:
- 所有测试通过；其中「演示重复退款会导致测试失败」的用例以 `xfail(strict=True)` 呈现。
- 总耗时 <10 秒（单场景 <5 秒）。
- 无网络请求，无真实 sleep。

## 分步验证

### 1. 无幂等键：检测到重复退款

```bash
pytest examples/refund/test_refund_lost_ack.py -q
```

**预期**:
- `test_duplicate_is_detected` 通过：报告 `ok=False`，包含 2 条 `refund` 的 `COMMITTED` 记录。
- `test_lost_ack_demo_fails` 为 xfail：内部调用 `report.assert_clean()`，抛
  `EffectSafetyError`，证明用户会看到真实失败。

查看完整失败报告：

```bash
pytest examples/refund/test_refund_lost_ack.py::test_lost_ack_demo_fails -q --runxfail
```

报告应包含：

```text
scenario=refund-lost-ack seed=7
[eff-000001] refund order-42 attempt=1 status=committed fault=timeout_after_commit
             run=run-0001 thread=thread-0001 checkpoint=<id>
[eff-000002] refund order-42 attempt=2 status=committed fault=None
             run=run-0001 thread=thread-0001 checkpoint=<id>
VIOLATION no_duplicate_effects: expected 1 committed refund, actual 2
          business_key=order-42 effect_ids=(eff-000001, eff-000002)
```

### 2. 加幂等键：测试通过

```bash
pytest examples/refund/test_refund_idempotent.py -q
```

**预期**: 通过。报告只有 1 条 committed `refund`；`SimulatedRefundService` 账本只有 1 笔。

### 3. Checkpoint 恢复

```bash
pytest examples/refund/test_refund_resume.py -q
```

**预期**:
- 恢复后不新增 committed `refund`（effect 在 checkpoint 之前已完成）。
- 报告按 `run-0001` / `run-0002` 区分片段。

### 4. Interrupt 重放

```bash
pytest examples/refund/test_refund_interrupt.py -q
```

**预期**:
- effect 位于 interrupt 之前的用例：恢复后重复，测试断言检测成功（用例通过）。
- effect 位于 interrupt 之后的用例：恢复后只有 1 笔 committed。

### 5. 确定性与离线

```bash
pytest tests/integration/test_determinism_and_offline.py -q
```

**预期**: 同场景同 seed 连续 20 次，effect 计数与结论完全一致；断网执行仍通过。

### 6. 覆盖率与静态检查

```bash
pytest --cov=agentreplayguard --cov-report=term-missing
ruff check .
mypy src/agentreplayguard
```

**预期**: 核心模块行覆盖率 ≥90%；ruff/mypy 无错误。

## 用户侧最小代码形态

以下仅示意接线方式，完整实现见 Phase 4：

```python
import pytest
from agentreplayguard import FaultKind, FaultPlan, FaultRule, NoDuplicateEffects
from agentreplayguard.adapters.langgraph import LangGraphAdapter

def test_lost_ack_detects_duplicate(replayguard, refund_scenario):
    scenario = replayguard(
        "refund-lost-ack",
        seed=7,
        faults=FaultPlan([
            FaultRule(
                kind=FaultKind.TIMEOUT_AFTER_COMMIT,
                effect_type="refund",
                attempt=1,
            )
        ]),
        invariants=[NoDuplicateEffects("refund")],
    )
    graph = build_refund_graph(scenario)  # 节点中的工具用 scenario.guard() 包装
    adapter = LangGraphAdapter(scenario, graph)
    adapter.invoke({"order_id": "order-42", "amount_cents": 1000})

    report = scenario.finish()
    assert not report.ok
    assert report.violations[0].invariant_name == "no_duplicate_effects"
```

关键接线点：
1. 副作用工具用 `scenario.guard().effect(...)` 包装。
2. `RetryPolicy` 显式设置 `retry_on=(TimeoutError, ConnectionError, ServiceError)`。
3. 示例设置 `initial_interval=0`、`jitter=False`。
4. `examples/refund/conftest.py` 提供 `refund_scenario` fixture，用
   `SimulatedRefundService` 替换真实服务；该 fixture 属于示例，不是库的公开 fixture。

## 故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| `ImportError: langgraph` | 未安装 optional extra | `pip install -e ".[langgraph]"` |
| 测试意外通过、没有重试 | 默认 `RetryPolicy` 不重试 `OSError` | 显式配置 `retry_on=(TimeoutError, ConnectionError, ...)` |
| 测试很慢 | 默认 backoff/jitter | `initial_interval=0`、`jitter=False` |
| `UnsupportedGraphError` | 并行 fan-out、无 checkpointer 或 graph API 不符 | 改为串行图；恢复场景加 `InMemorySaver` |
| `ScenarioConfigError: business key` | key 参数名不存在或值为空 | 检查工具签名与 `key=` 配置 |
| 报告没有 effect | 工具未用 guard 包装，或副作用在未包装的子图内 | 包装工具，或把子图副作用上移到可包装层 |
| `IdempotencyConflict` | 同幂等键但参数不同 | 这是预期行为；检查键是否随状态稳定派生 |

## 验收映射

| Quickstart 步骤 | 对应标准 |
|-----------------|----------|
| 安装 + 运行全部示例 | SC-001（10 分钟内跑通） |
| 步骤 1、3、4 | SC-002（至少三类路径复现） |
| 步骤 1 + 2 | SC-003（无键失败、有键通过） |
| 步骤 5 | SC-004、SC-008 |
| 全流程计时 | SC-005（单场景 <5 秒） |
| 步骤 6 | SC-007（覆盖率 ≥90%） |

SC-006（报告可用性）需要 3 名目标用户参与，按产品定位文档中的验证计划单独执行。
