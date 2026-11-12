# Implementation Plan: AgentReplayGuard MVP — LangGraph 副作用安全测试

**Branch**: `001-effect-safety-testing` | **Date**: 2026-11-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-effect-safety-testing/spec.md`

## Summary

构建一个 Python 库 `agentreplayguard`，让用户在不改写 LangGraph 业务图的前提下，用显式
effect guard 包裹有副作用的工具调用，配合确定性故障计划、内存 Effect Store、退款模拟服务
与不变量检查，在 pytest 中断言「重试 / Checkpoint 恢复 / Interrupt 重放不会重复提交业务
副作用」。

技术路线：核心模块零第三方依赖；LangGraph 隔离在可选适配层；副作用拦截采用显式包装而非
monkeypatch；故障由规则 + seed 决定；时间与 ID 使用逻辑时钟；MVP 只支持串行图。

## Technical Context

**Language/Version**: Python 3.10–3.13（与 LangGraph 1.2 的最低要求一致；3.14 暂不纳入发布矩阵）

**Primary Dependencies**: 运行时核心仅标准库；可选 extra `langgraph>=1.2,<2.0`（已核对 PyPI
1.2.20，2026-11-05 发布，要求 Python >=3.10）；开发依赖 `pytest>=8`、`pytest-cov`、`ruff`、
`mypy`

**Storage**: 进程内内存（Effect Store、模拟账本、InMemorySaver）；无持久化

**Testing**: pytest + pytest-cov；单元、契约、LangGraph 集成测试；断网 CI 任务

**Target Platform**: Linux、macOS；Windows best-effort

**Project Type**: 单包 Python 库 + pytest 插件

**Performance Goals**: 单个典型场景 <5 秒；无真实 sleep（示例 RetryPolicy 使用
`initial_interval=0`、`jitter=False`）

**Constraints**: 无网络；确定性轨迹；仅串行图；核心不 import langgraph；Python 3.10+

**Scale/Scope**: 5 个核心模块 + 1 个适配器 + 1 个模拟服务 + 1 个退款示例；MVP 约 1.5–2k 行

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 闸门 | 结论 |
|------|------|------|
| I. 真实需求优先 | 规格引用 Phase 0 已核实的 LangGraph 文档与 Issues；未完成验证项已列入假设 | PASS |
| II. 确定性可复现 | 逻辑时钟 + 固定 seed + 规则化故障；记录中不含 wall clock；无网络 | PASS |
| III. 默认模拟 | 退款服务、故障、账本均在进程内；不内置真实供应商客户端 | PASS |
| IV. 测试先行 | tasks 阶段按模块先写失败测试；核心覆盖率 ≥90% 作为合并闸门 | PASS（计划约束） |
| V. 小接口面 | 公开面 = Scenario + EffectGuard + EffectStore 查询 + 不变量 + Report + Adapter | PASS |
| VI. 模块化边界 | 核心不 import langgraph；适配器单独 optional extra；服务可替换 | PASS |
| VII. 克制范围 | 仅串行图、4 类恢复路径、3 类不变量、1 个示例；无持久化/异步/多框架 | PASS |
| VIII. 失败可解释 | Report 固定包含 effect 类型、业务键、哈希、attempt、状态、run/thread/checkpoint、期望/实际 | PASS |

**Post-design re-check**: 设计未引入新依赖、新存储或额外框架；无违反项，Complexity Tracking
为空。

## Project Structure

### Documentation (this feature)

```text
specs/001-effect-safety-testing/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── public-api.md
│   └── langgraph-adapter.md
├── checklists/
│   └── requirements.md
└── tasks.md              # /speckit-tasks 生成，不在本阶段创建
```

### Source Code (repository root)

```text
src/agentreplayguard/
├── __init__.py           # 唯一公开导出面
├── py.typed
├── errors.py             # EffectSafetyError / ScenarioConfigError / UnsupportedGraphError
├── clock.py              # LogicalClock、确定性 ID 生成
├── effects.py            # EffectStatus、EffectRecord、EffectStore、EffectView
├── faults.py             # FaultKind、FaultRule、FaultPlan、FaultInjector、FaultDirective
├── guard.py              # EffectGuard：参数绑定、哈希、attempt、提交/故障语义
├── invariants.py         # Invariant 协议、NoDuplicateEffects、MaxEffectCount、CustomInvariant
├── scenario.py           # Scenario：装配 store/clock/injector/invariants，生命周期
├── report.py             # ScenarioReport、RunSegment、Violation、文本格式化
├── pytest_plugin.py      # replayguard fixture，pytest11 entry point
├── services/
│   ├── __init__.py
│   └── refund.py         # SimulatedRefundService、Refund、IdempotencyConflict
└── adapters/
    ├── __init__.py
    └── langgraph.py      # LangGraphAdapter：invoke / resume / interrupt_resume / state

tests/
├── unit/
│   ├── test_effects.py
│   ├── test_faults.py
│   ├── test_guard.py
│   ├── test_invariants.py
│   └── test_report.py
├── contract/
│   └── test_public_api.py
└── integration/
    ├── test_langgraph_retry.py
    ├── test_langgraph_resume.py
    ├── test_langgraph_interrupt.py
    └── test_determinism_and_offline.py

examples/refund/
├── graph.py              # 退款 LangGraph 图（串行）
├── tools.py              # 被 guard 包裹的退款/通知工具
├── test_refund_lost_ack.py
├── test_refund_idempotent.py
├── test_refund_resume.py
├── test_refund_interrupt.py
└── test_refund_partial.py

docs/
├── product-positioning.md
├── quickstart.md         # 面向用户的快速开始（发布阶段完善）
└── architecture.md       # 发布阶段由本计划提炼
```

**Structure Decision**: 采用单包 `src/` 布局。核心（effects/faults/guard/invariants/scenario/
report）只依赖标准库；`adapters/langgraph.py` 是唯一 import langgraph 的模块，通过 optional
extra 安装。`services/refund.py` 是参考模拟实现，不作为核心依赖。测试按 unit/contract/
integration 分层，契约测试锁定公开 API 行为。

## Test Strategy

- **单元测试**（无 LangGraph）：Effect Store 查询与去重口径、FaultRule 匹配与 times 消耗、
  guard 参数绑定/哈希/提交状态、内置不变量、报告确定性格式。
- **契约测试**：公开导入面、异常类型与继承关系、pytest fixture、报告字段、`assert_clean`
  的失败消息；契约变更必须同步更新 `contracts/public-api.md`。
- **集成测试**：LangGraph 重试、checkpoint 恢复、interrupt 恢复、默认 retry_on 不重试
  `OSError`、串行图检查、20 次确定性、断网运行。
- **TDD**：每个模块先写失败测试（原则 IV）；核心模块覆盖率 ≥90%，公开 API 至少一个正向
  + 一个边界用例。
- **版本矩阵**：Python 3.10–3.13；LangGraph 1.2.20 与一个较早 1.2.x；Linux 与 macOS；
  Windows best-effort。
- **性能**：测试中不使用真实 sleep；示例 RetryPolicy 使用 `initial_interval=0`、
  `jitter=False`；单场景 <5 秒作为验收而非硬性 CI 超时（避免机器抖动）。

## Technical Risks

| 风险 | 影响 | 缓解措施 | 验证方式 |
|------|------|----------|----------|
| 默认 RetryPolicy 不重试 OSError，示例可能静默变成「安全」 | 高：核心结论错误 | 文档显著提示；示例显式 retry_on；集成测试锁定默认行为 | 默认 vs 显式两组测试 |
| LangGraph 2.x 或 1.2.x 小版本 API 漂移 | 高：适配器失效 | 限制 `<2.0`；只用公共 API；版本矩阵；适配器隔离 | CI 矩阵 |
| 用户忘记包裹工具，报告显示无 effect | 高：假阴性 | Quickstart 强调；无 effect 时 warning；文档列出常见漏包位置 | 示例与可用性测试 |
| 幂等键去重口径假设服务端遵守键 | 中：真实服务结论不可信 | MVP 只用内置模拟服务；文档声明假设；接入真实服务需用户确认 | 模拟服务冲突测试 |
| Checkpoint 归属为片段级，非每个 effect 精确 checkpoint | 中：多 effect 场景定位变粗 | 报告展示 run/thread/checkpoint_before/after；文档声明限制 | US3 场景验证 |
| 串行图静态检查误报/漏报 | 中：条件边被误判为并行 | `strict_graph=False` 逃生开关；先发版收集反馈；P2 改进 | get_graph 行为测试 |
| 部分成功需要多 effect 组合建模 | 中：单次调用无法表达 | 文档给出「多步业务拆成多个 guarded call」模式；示例覆盖 | partial-success 示例 |
| 真实时间/随机数泄漏进报告 | 中：破坏确定性 | 逻辑时钟、固定 seed、无 UUID；报告格式测试 | 20 次一致性测试 |
| 需求假设未验证（H1–H6） | 高：产品方向 | Phase 0 遗留验证项在发布前补做；不扩范围 | 用户访谈/试用 |
| 名称 Replay 被误解为流量回放 | 中：定位沟通成本 | 发布前 5 人命名测试；必要时更名（EffectGuard/AgentEffect） | 命名测试 |

## Complexity Tracking

无违反 Constitution Check 的设计项，无需例外说明。
