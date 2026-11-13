# AgentReplayGuard

面向 **LangGraph + pytest** 的副作用安全测试工具：用确定性的故障注入与 effect 账本，验证
重试、Checkpoint 恢复与 Interrupt 重放不会重复执行支付、退款、写入、通知等业务操作。

> MVP 核心实现已完成（US1–US6），并已补齐异步工具、异步图执行、HTTP 传输层故障注入与
> 并行 fan-out 图支持；当前覆盖 lost-ack 重复副作用、幂等键、Checkpoint 恢复、Interrupt
> 重放、业务不变量、并行分支重复副作用与确定性回归。

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
- [x] Phase 5 开源发布（[GitHub 仓库](https://github.com/HangChi/AgentReplayGuard)、[v0.1.0 Release](https://github.com/HangChi/AgentReplayGuard/releases/tag/v0.1.0)）

## 快速开始

```bash
uv sync --extra dev --extra langgraph --extra httpx
uv run pytest examples/refund -q
```

用户接入说明见 [docs/quickstart.md](docs/quickstart.md)，完整验收步骤见
[quickstart.md](specs/001-effect-safety-testing/quickstart.md)。

## 核心概念

| 模块 | 职责 |
|------|------|
| Effect Store | 记录每次副作用尝试：类型、业务键、参数哈希、尝试序号、提交状态、run/thread/checkpoint、branch |
| Fault Injector | 五类故障（提交前超时、提交后响应丢失、连接重置、500、部分成功），固定 seed |
| Simulated Service | 退款账本 + 幂等键开关 |
| Invariant Checker | `no_duplicate_effects`、`max_effect_count`、`concurrent_commit`、自定义 predicate |
| LangGraph Adapter | 驱动 RetryPolicy / resume / interrupt，支持同步/异步与并行 fan-out，记录节点分支归属 |
| HTTP Transport Adapter | 包裹 httpx 同步/异步 transport，业务代码零改动地记账并注入 lost-ack |

## 许可

MIT License。详见 [LICENSE](LICENSE)。

## 参与贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。
