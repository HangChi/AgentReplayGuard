# Implementation Plan: 并发与并行图的副作用竞态与线性一致性检测

**Branch**: `004-concurrent-parallel-graph` | **Date**: 2026-11-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-concurrent-parallel-graph/spec.md`

## Summary

把 `LangGraphAdapter` 对并行扇出（fan-out）的「入口拒绝」改为「识别 + 支持 + 检测」：
识别图结构中一个节点有 >1 条无条件出边的 fan-out，为每个分支分配确定性 `branch_id`，在
分支执行期间通过 contextvar 注入，`EffectGuard` 读取并写入 `EffectRecord.branch_id` 扩展字段。
`NoDuplicateEffects` 复用既有去重口径即可检测「并行分支提交同一业务键」，并借助 `branch_id`
在报告中区分违规来源。新增「并发提交」判定（基于 `started_tick`/`ended_tick` 区间重叠）覆盖
异步交错/手动并发场景。核心模块保持不 import LangGraph，框架隔离与确定性语义不变。

## Technical Context

**Language/Version**: Python ≥ 3.10（CI 覆盖 3.10–3.13）

**Primary Dependencies**: 核心运行时仅标准库，无新增第三方依赖；`contextvars` 为标准库。
LangGraph 1.2.x 仍作为可选 extra 隔离在适配器层。

**Storage**: 复用进程内 Effect Store；`EffectRecord` 增加 `branch_id` 字段（无持久化新增）。

**Testing**: pytest；同步/异步均用标准库 `asyncio.run`，不引入 pytest-asyncio；fan-out 图用
`Annotated` reducer 保证 channel 写合法，全部进程内离线运行。

**Target Platform**: Linux、macOS（Windows best-effort）

**Project Type**: 单包 Python 库（pytest 插件形态）

**Performance Goals**: 单个典型 fan-out 场景 <5 秒；无真实网络与真实延迟

**Constraints**: 断网可运行；确定性（seed/逻辑时钟/确定性分支编号驱动）；核心包导入不得因
缺少 LangGraph 失败；现有公开 API 语义不变（仅扩展 `EffectRecord` 字段）；覆盖率 ≥90%

**Scale/Scope**: 扩展 `EffectRecord`（1 字段）、`adapters/langgraph.py`（fan-out 识别与上下文
注入）、新增 `ConcurrentCommitDetected` 不变量与并发判定工具、约 4 个测试文件 + 1 个示例；
不改变 guard/fault 语义、不引入新核心依赖

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 结论 | 说明 |
|------|------|------|
| I. 真实需求优先 | PASS | 证据：竞品调研（research R-02）确认无工具在「测试定位」下覆盖并行 fan-out 副作用竞态检测；并行是重复副作用的独立来源（工程事实） |
| II. 确定性可复现 | PASS | 关键论证：LangGraph 1.2.20 的 fan-out 是「superstep 内确定性顺序调度」而非真并发（research R-03 实测，同步/异步各 5 次均稳定）。真线程/多进程并发明确列为 Out of Scope。异步交错场景用区间重叠判定，不对记录重排序，故同一 seed 下轨迹可复现 |
| III. 默认模拟外部服务 | PASS | 示例与测试仅用进程内模拟服务；不引入任何真实供应商客户端 |
| IV. 测试先行 | PASS | 先写 fan-out 识别/归属/并发检测的失败测试，再实现；新增模块纳入覆盖率 |
| V. 小接口面与显式契约 | PASS | 仅扩展 `EffectRecord` 一个字段、新增一个不变量与一个判定函数；不改既有公开签名；契约文档化 |
| VI. 模块化与可替换边界 | PASS | 分支归属注入在适配器层完成；核心模块（guard/effects/invariants/report）不 import LangGraph，通过 contextvar 与字段通信 |
| VII. 克制范围（YAGNI） | PASS | 只做 fan-out 支持 + 并行重复检测 + 异步交错并发判定；不做真线程/多进程、完整线性化算法、流式、其他框架/客户端 |
| VIII. 失败可解释 | PASS | 报告经 `branch_id` 扩展，能定位「哪个 key 被哪些分支重复提交」；effect 类型/业务键/attempt 归属信息齐备 |

**Gate result**: 全部通过，无需例外说明。

## Project Structure

### Documentation (this feature)

```
specs/004-concurrent-parallel-graph/
├── spec.md              # 特性规格（本文件已提交）
├── plan.md              # 本文件
├── research.md          # 调研结论（R-01~R-06）
├── data-model.md        # EffectRecord.branch_id 与 BranchContext
├── contracts/
│   └── branch-attribution.md   # 分支归属与并发判定契约
├── quickstart.md        # 并行图使用与验证步骤
├── checklists/
│   └── requirements.md  # 需求核对清单
└── tasks.md             # 实现任务清单
```

### Source Code (this feature)

```
src/agentreplayguard/
├── effects.py           # EffectRecord 增加 branch_id 字段
├── context.py           # 新增：BranchContext contextvar 管理
├── invariants.py        # 新增 ConcurrentCommitDetected 不变量
├── adapters/langgraph.py# fan-out 识别 + 分支上下文注入
└── report.py            # 报告含 branch_id（若需 format 扩展）
```

## 设计要点

### 1. fan-out 识别（沿用 `_find_fanout`，语义反转）

`_find_fanout()` 已能返回「有 >1 条无条件出边的 source 节点列表」。本特性把「发现即拒绝」
改为「发现即建立分支映射」。需要额外的图遍历来为每条出边确定 `branch_id`。

### 2. 确定性 branch_id 分配

对 fan-out 节点，按 `get_graph().edges` 的**注册顺序**（`source, target` 字典序或注册序）为
每条出边目标分配 `branch_id`。分支编号必须稳定（同一图结构下一致），避免依赖运行时顺序。

### 3. contextvar 注入

标准库 `contextvars.ContextVar`。适配器在 `invoke`/`ainvoke` 期间，为每个分支设置对应的
`branch_id`。因 LangGraph fan-out 是顺序调度（无真并发），单 contextvar 即可表达「当前正在
执行的分支」。`EffectGuard._begin_attempt` 读取当前 contextvar 值写入 `EffectRecord.branch_id`。

### 4. 并发提交判定

`started_tick`/`ended_tick` 已是单调逻辑时钟。区间重叠判定：两条 COMMITTED 记录同
business_key 且 `[started, ended]` 区间相交（`a.started < b.ended and b.started < a.ended`）即
为并发。不变量 `ConcurrentCommitDetected` 复用此判定。

### 5. 复杂度跟踪（Complexity Tracking）

| 复杂度 | 说明 | 更简单方案为何被否决 |
|--------|------|----------------------|
| 新增 `context.py` 与 contextvar | 分支归属注入 | 用 `langgraph.config` 读运行时 node id（R-05 否决）：依赖内部实现，易漂移；contextvar 是标准库且框架无关 |
| 图遍历确定 branch_id | 分支确定性编号 | 用执行时顺序（R-06 否决）：依赖调度，不确定 |
| 区间重叠判定 | 并发提交检测 | 对记录重排序（R-06 否决）：放大不确定性；区间判定保持「追加即顺序」简单语义 |

## 阶段划分

1. **Phase 0 前置**：版本号 bump 到 0.4.0，锁 baseline（全量测试 + ruff + mypy + coverage 基线）
2. **Phase 1 数据模型**：`EffectRecord.branch_id` + `context.py`（失败测试先行）
3. **Phase 2 US1**：fan-out 识别 + 分支上下文注入（适配器层）
4. **Phase 3 US2**：并行重复检测（复用 NoDuplicateEffects + branch_id 报告）
5. **Phase 4 US3**：并发提交判定（区间重叠 + ConcurrentCommitDetected）
6. **Phase 5 文档与示例**：quickstart + examples + README
7. **Phase 6 全量验证**：pytest + ruff + mypy + coverage ≥90%
