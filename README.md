# AgentReplayGuard

面向 **LangGraph + pytest** 的副作用安全测试工具：用确定性的故障注入与 effect 账本，验证
重试、Checkpoint 恢复与 Interrupt 重放不会重复执行支付、退款、写入、通知等业务操作。

> MVP 核心实现已完成（US1–US6），并已补齐异步工具、异步图执行、HTTP 传输层故障注入、
> 并行 fan-out 图支持、流式接口、requests 适配器、多框架工具接入、报告导出与 JUnit 报告；
> 当前覆盖 lost-ack 重复副作用、幂等键、Checkpoint 恢复、Interrupt 重放、业务不变量、
> 并行分支重复副作用、流式归属与确定性回归。内置退款、订单、邮件、库存四类模拟服务模板。

## 它解决什么问题

AI Agent 调用有副作用的工具时，失败语义与普通函数不同：

1. 服务端已提交（如退款成功），但响应丢失，Agent 认为失败并重试 → 两笔退款。
2. LangGraph 的 durability 保证图状态恢复，但不保证外部副作用 exactly-once。
3. interrupt 恢复会从头重跑节点，放在 interrupt 之前的副作用可能再次执行。

传统 mock 验证「调用了几次」，无法表达「服务端提交了几次」。AgentReplayGuard 把业务
副作用的最终一致性变成可在 CI 中断言的属性。

## 现状与路线图

- [x] Phase 0 调研与需求验证
- [x] Phase 1 产品定义（[产品定位](docs/product-positioning.md)、[MVP 规格](specs/001-effect-safety-testing/spec.md)）
- [x] Phase 2 技术架构（[实现计划](specs/001-effect-safety-testing/plan.md)、[公开 API 契约](specs/001-effect-safety-testing/contracts/public-api.md)）
- [x] Phase 3 项目初始化
- [x] Phase 4 MVP 开发（[任务清单](specs/001-effect-safety-testing/tasks.md)）
- [x] 异步工具与异步图执行（[002 规格](specs/002-async-execution-support/spec.md)）
- [x] HTTP 故障注入传输层（[003 规格](specs/003-http-fault-transport/spec.md)）
- [x] 并发与并行图副作用竞态检测（[004 规格](specs/004-concurrent-parallel-graph/spec.md)）
- [x] 流式接口的副作用归属与故障注入（[005 规格](specs/005-streaming-fault-injection/spec.md)）
- [x] requests 客户端适配器（[006 规格](specs/006-requests-adapter/spec.md)）
- [x] 多框架工具副作用记账（[007 规格](specs/007-multi-framework-tools/spec.md)）
- [x] 报告结构化导出（[008 规格](specs/008-report-export/spec.md)）
- [x] 流式响应体丢失语义（[009 规格](specs/009-stream-body-loss/spec.md)）
- [x] 同步 stream 入口（[010 规格](specs/010-sync-stream/spec.md)）
- [x] CI 报告格式（JUnit XML）（[011 规格](specs/011-junit-report/spec.md)）
- [x] 更多模拟服务模板（订单/邮件/库存）（[012 规格](specs/012-more-simulated-services/spec.md)）
- [x] 场景自动断言（消除静默漏报）（[013 规格](specs/013-auto-assert-scenario/spec.md)）
- [x] Phase 5 开源发布（[GitHub 仓库](https://github.com/HangChi/AgentReplayGuard)、[v0.1.0 Release](https://github.com/HangChi/AgentReplayGuard/releases/tag/v0.1.0)）

## 快速开始

### 安装

```bash
# 最小安装：核心包仅依赖标准库
pip install agentreplayguard

# 按需安装适配层（可组合）
pip install "agentreplayguard[langgraph]"   # LangGraph 图适配
pip install "agentreplayguard[httpx]"       # httpx 传输层故障注入
pip install "agentreplayguard[requests]"    # requests 客户端适配
pip install "agentreplayguard[agents]"      # OpenAI Agents SDK 工具
```

用 `uv` 等价写法：`uv add agentreplayguard --extra langgraph`。

### 从源码开发

```bash
uv sync --extra dev --extra langgraph --extra httpx --extra requests --extra agents
uv run pytest examples/refund -q
```

用户接入说明见 [docs/quickstart.md](docs/quickstart.md)，完整验收步骤见
[quickstart.md](specs/001-effect-safety-testing/quickstart.md)，版本演进见
[CHANGELOG.md](CHANGELOG.md)。

### pytest 最小示例

`replayguard` fixture 由插件自动注册（无需 import）：声明场景后，**测试结束会自动检查
副作用安全性**，有违规即 FAILED——忘记写断言也不会静默通过。

```python
from agentreplayguard import FaultKind, FaultPlan, FaultRule, NoDuplicateEffects


# examples/refund/test_refund_idempotent.py 的简化版
def test_refund_lost_ack(replayguard):
    scenario = replayguard(
        "refund-lost-ack",
        seed=7,
        faults=FaultPlan(
            [
                FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1),
            ]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )
    # 用 scenario.guard().effect(...) 包裹有副作用的工具，跑业务流程……
    # 无需手动 assert：出现重复退款时本测试自动 FAILED
```

如需细粒度断言（如具体笔数），仍可显式读报告——两者不冲突，也不会重复报错：

```python
report = scenario.finish()
assert not report.ok
assert scenario.effects.committed_count("refund") == 2
```

## 核心概念

| 模块 | 职责 |
|------|------|
| Effect Store | 记录每次副作用尝试：类型、业务键、参数哈希、尝试序号、提交状态、run/thread/checkpoint、branch |
| Fault Injector | 六类故障（提交前超时、提交后响应丢失、连接重置、500、部分成功、流式响应体丢失），固定 seed |
| Simulated Service | 退款/订单/邮件/库存四类模拟服务：内存账本 + 幂等键开关（参考实现，供仿照接入） |
| Invariant Checker | `no_duplicate_effects`、`max_effect_count`、`concurrent_commit`、自定义 predicate |
| pytest 集成 | `replayguard` fixture 自动断言：测试结束后检查场景，有违规即 FAILED（忘记写断言也不会漏报） |
| LangGraph Adapter | 驱动 RetryPolicy / resume / interrupt / stream / astream，支持同步/异步与并行 fan-out，记录节点分支归属 |
| HTTP Transport Adapter | 包裹 httpx 同步/异步 transport 与 requests adapter，业务代码零改动地记账并注入 lost-ack |

## 许可

MIT License。详见 [LICENSE](LICENSE)。

## 参与贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。
