# Implementation Plan: 异步副作用安全测试

**Branch**: `002-async-execution-support` | **Date**: 2026-11-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-async-execution-support/spec.md`

## Summary

为现有同步测试能力补齐异步路径：`EffectGuard` 自动识别异步工具并提供异步调用入口，
`LangGraphAdapter` 提供异步执行与异步恢复入口。异步路径复用同一 Effect Store、故障注入器、
不变量与报告结构，保证同一 seed 下与同步路径产生完全一致的记账与结论。核心修复点是：
当前同步 wrapper 包裹 `async def` 会把协程对象当作成功结果并记为 `committed`，必须改为
在同步入口显式拒绝，避免测试假通过。

## Technical Context

**Language/Version**: Python ≥ 3.10（CI 覆盖 3.10–3.13）

**Primary Dependencies**: 运行时仅标准库（新增使用 `asyncio`、`inspect`）；`langgraph>=1.2,<2.0`
为可选 extra，仅在适配层导入

**Storage**: 进程内内存（现有 Effect Store 与模拟账本），无新增存储

**Testing**: pytest；异步测试使用标准库 `asyncio.run` 驱动，不引入 pytest-asyncio/anyio

**Target Platform**: Linux、macOS（Windows best-effort）

**Project Type**: 单包 Python 库（pytest 插件形态）

**Performance Goals**: 单个典型异步场景 <5 秒；不引入真实 sleep 或网络等待

**Constraints**: 断网可运行；确定性（无真实时钟/随机源）；同步公开 API 向后兼容；
核心包不得依赖 langgraph；覆盖率 ≥90%

**Scale/Scope**: 新增 2 个公开异步方法组（guard、adapter），1 个异步示例，约 300–400 行
源码与测试增量；不引入并发、流式接口与新的测试运行器

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 结论 | 说明 |
|------|------|------|
| I. 真实需求优先 | PASS | 证据为现有同步 wrapper 对 async 函数的错误记账（可复现缺陷），以及异步 LangGraph 用户无法使用适配器 |
| II. 确定性可复现 | PASS | 异步路径不引入真实延迟/网络；逻辑时钟与 seed 驱动保持不变；取消仅记录状态不入调度 |
| III. 默认模拟外部服务 | PASS | 复用内存模拟退款服务，无真实调用 |
| IV. 测试先行 | PASS | 先写异步 guard/adapter 失败测试；新增模块纳入覆盖率统计，整体 ≥90% |
| V. 小接口面与显式契约 | PASS | 仅扩展 `EffectGuard.acall` 与适配器三个异步方法；同步签名不变；契约文档新增 |
| VI. 模块化与可替换边界 | PASS | 异步能力仅改 guard 与 LangGraph 适配器；核心模块不 import langgraph |
| VII. 克制范围（YAGNI） | PASS | 不做 `astream`、并发、竞态检测、新运行器依赖；无新第三方依赖 |
| VIII. 失败可解释 | PASS | 复用既有报告结构，异步失败同样输出 effect 类型、业务键、attempt、run/thread/checkpoint |

**Gate result**: 全部通过，无需例外说明。设计后复检仍全部通过（见文末）。

## Project Structure

### Documentation (this feature)

```text
specs/002-async-execution-support/
├── plan.md              # 本文件
├── research.md          # Phase 0：技术决策与替代方案
├── data-model.md        # Phase 1：复用与新增的数据语义
├── quickstart.md        # Phase 1：异步路径验收步骤
├── contracts/
│   └── public-api-additions.md  # Phase 1：异步公开 API 契约
├── checklists/
│   └── requirements.md  # 规格质量检查表
└── tasks.md             # Phase 2 输出（/speckit-tasks 生成）
```

### Source Code (repository root)

```text
src/agentreplayguard/
├── __init__.py
├── guard.py                     # 新增 async 自动识别、acall、同步误用拒绝
├── adapters/langgraph.py        # 新增 ainvoke / aresume / aresume_interrupt
├── effects.py                   # 复用（可能补充 UNKNOWN 语义文档）
├── faults.py                    # 复用
├── invariants.py                # 复用
├── report.py                    # 复用
└── scenario.py                  # 复用

tests/
├── unit/
│   ├── test_guard_async.py      # 新增：异步记账、故障、异常、取消、误用
│   └── test_adapter_async.py    # 新增：异步方法前置条件（假 graph stub）
├── integration/
│   └── test_langgraph_async.py  # 新增：ainvoke / aresume / interrupt / 同步等价
└── contract/
    └── test_public_api.py       # 扩展：异步公开签名与兼容性

examples/refund/
├── tools_async.py               # 新增：异步退款工具
├── graph_async.py               # 新增：异步节点图
└── test_refund_async.py         # 新增：异步 lost-ack 示例

docs/quickstart.md               # 增加异步用法与常见错误
README.md                        # 更新能力说明
pyproject.toml                   # 版本与说明（如需）
```

**Structure Decision**: 沿用现有单包 `src/` 布局与 `tests/{unit,integration,contract}` 分层；
异步能力是现有模块的并行执行路径，不新建包或子系统。

## Complexity Tracking

无违反项，无需填写。

## Post-Design Constitution Re-Check

| 原则 | 结论 | 设计后说明 |
|------|------|------------|
| I / II / III | PASS | 设计不改变证据链、确定性或模拟边界 |
| IV | PASS | 测试清单覆盖正向、故障、异常、取消、误用与同步等价 |
| V | PASS | 契约新增仅 4 个方法，均为既有语义的异步镜像 |
| VI / VII | PASS | 未新增依赖或子系统；明确排除流式与并发 |
| VIII | PASS | 报告复用，不新增第二套格式 |
