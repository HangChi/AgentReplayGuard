---
description: "Task list for AgentReplayGuard 002 异步副作用安全测试"
---

# Tasks: 002 异步副作用安全测试

**Input**: Design documents from `/specs/002-async-execution-support/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: 测试先行是强制要求（宪法原则 IV）。每个模块先写失败测试，再实现。

**Organization**: 按用户故事分组，每个故事可独立实现与验证。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件，无依赖）
- **[Story]**: 所属用户故事（US1–US4）

## Path Conventions

- 单包 `src/` 布局；测试分 `tests/unit`、`tests/contract`、`tests/integration`。
- 新增公开 API 契约见 `specs/002-async-execution-support/contracts/public-api-additions.md`。

---

## Phase 1: Setup

**Purpose**: 确认基线与工作分支（无新建工程骨架）。

- [x] T001 确认当前分支为 `002-async-execution-support` 且 `specs/002-async-execution-support/` 设计文档齐全
- [x] T002 运行 `uv run pytest -q` 与 `uv run ruff check .`，记录同步基线全绿（作为异步改造的回归基线）

---

## Phase 2: Foundational

**Purpose**: 在不改变同步行为的前提下，抽出同步/异步共享的记账辅助结构。

**⚠️ CRITICAL**: 本阶段完成后才能开始异步用户故事。

- [x] T003 在 `src/agentreplayguard/guard.py` 中抽出私有尝试上下文（参数绑定、业务键/参数哈希、attempt 分配、故障指令、run 上下文、记录写入），同步 `call` 改为使用该辅助结构，行为不变
- [x] T004 运行现有 `tests/unit/test_guard.py`、`tests/unit/test_scenario.py`、`tests/contract/test_public_api.py`，确认重构无回归

**Checkpoint**: 共享记账辅助就绪，同步路径全绿。

---

## Phase 3: User Story 1 — 异步工具被正确记账并注入故障 (Priority: P1) 🎯 MVP

**Goal**: `effect` 自动识别异步工具，`acall` 提供异步执行路径，记账与故障语义和同步一致。

**Independent Test**: 运行 `tests/unit/test_guard_async.py`，异步 lost-ack 场景得到 2 条 committed。

### Tests for User Story 1 ⚠️

- [x] T005 [P] [US1] 编写 `tests/unit/test_guard_async.py`：异步正常提交（1 条 committed、返回真实值）、异步 lost-ack（2 条 committed、attempt 1/2、业务键与参数哈希一致）、提交前故障（不执行函数且 not_committed）、业务异常（not_committed 且原样传播）、取消（unknown 且传播 `CancelledError`）
- [x] T006 [P] [US1] 扩展 `tests/contract/test_public_api.py`：`EffectGuard.acall` 存在且签名包含 `key`、`params`、`idempotency_key`；`effect` 装饰异步函数返回可 await 的 wrapper

### Implementation for User Story 1

- [x] T007 [US1] 在 `src/agentreplayguard/guard.py` 中实现 `inspect.iscoroutinefunction` 自动识别与异步 wrapper，新增 `async def acall(...)`，复用 T003 的共享记账辅助，取消记录 `EffectStatus.UNKNOWN`
- [x] T008 [P] [US1] 新增 `examples/refund/tools_async.py`：异步退款与异步通知工具，使用 `@scenario.guard().effect(...)` 声明业务键与幂等键
- [x] T009 [US1] 新增 `examples/refund/test_refund_async.py`：异步 lost-ack 检测重复退款、异步幂等键场景通过，使用 `asyncio.run` 驱动

**Checkpoint**: US1 可独立验证（异步记账与故障注入）。

---

## Phase 4: User Story 2 — 异步驱动 LangGraph 图 (Priority: P1)

**Goal**: 适配器提供 `ainvoke`，异步执行含异步节点的图并保持 run 片段、effect 归属与报告一致。

**Independent Test**: 运行 `tests/integration/test_langgraph_async.py`，异步 lost-ack 被检测且与同步结论一致。

### Tests for User Story 2 ⚠️

- [x] T010 [P] [US2] 编写 `tests/unit/test_adapter_async.py`：用假 graph stub 验证 `ainvoke` 调用 `graph.ainvoke`、记录 run 片段、缺少 `ainvoke` 抛 `UnsupportedGraphError`
- [x] T011 [P] [US2] 编写 `tests/integration/test_langgraph_async.py`：含异步节点的图首次执行为 COMMITTED；异步 lost-ack 重试后产生 2 条 committed；同步与异步等价场景的 effect 数量、状态序列与 attempt 一致

### Implementation for User Story 2

- [x] T012 [US2] 在 `src/agentreplayguard/adapters/langgraph.py` 中抽出共享 run 片段构建逻辑，实现 `async def ainvoke(...)`（延迟校验 `ainvoke` 能力）
- [x] T013 [P] [US2] 新增 `examples/refund/graph_async.py`：异步节点图（含 `retry_policy`、`initial_interval=0`、`jitter=False`）
- [x] T014 [US2] 在 `examples/refund/test_refund_async.py` 中补充基于异步图的 lost-ack 用例，并断言异步与同步报告结论一致

**Checkpoint**: US1 + US2 可独立验证。

---

## Phase 5: User Story 3 — 异步恢复：Checkpoint 与 Interrupt (Priority: P2)

**Goal**: 适配器提供 `aresume` 与 `aresume_interrupt`，恢复语义与同步一致。

**Independent Test**: 运行 `tests/integration/test_langgraph_async_resume.py` 与异步示例恢复用例。

### Tests for User Story 3 ⚠️

- [x] T015 [P] [US3] 编写 `tests/integration/test_langgraph_async_resume.py`：effect 在 checkpoint 后恢复不新增、effect 在 checkpoint 前恢复新增并被检测；interrupt 前有 effect 恢复后重复、interrupt 后有 effect 恢复后不重复；`aresume_interrupt` 无前次中断抛 `ScenarioConfigError`
- [x] T016 [P] [US3] 扩展 `tests/unit/test_adapter_async.py`：`aresume` 无前次 run 抛 `ScenarioConfigError`、无 checkpointer 抛 `UnsupportedGraphError`

### Implementation for User Story 3

- [x] T017 [US3] 在 `src/agentreplayguard/adapters/langgraph.py` 中实现 `async def aresume(...)` 与 `async def aresume_interrupt(...)`，复用同步入口的前置条件与 run 片段逻辑
- [x] T018 [P] [US3] 新增 `examples/refund/test_refund_async_resume.py`：异步 checkpoint 恢复与 interrupt 重放两个场景

**Checkpoint**: US1–US3 均可独立验证。

---

## Phase 6: User Story 4 — 误用被明确拒绝 (Priority: P2)

**Goal**: 同步入口执行异步工具时立即失败，账本零污染。

**Independent Test**: 运行 `tests/unit/test_guard_async_misuse.py`。

### Tests for User Story 4 ⚠️

- [x] T019 [P] [US4] 编写 `tests/unit/test_guard_async_misuse.py`：`call` 传入 `async def` 抛 `ScenarioConfigError`、错误信息含 `acall`/await 提示、账本 `records` 为空且 attempt 未累计；`acall` 传入同步函数正常执行

### Implementation for User Story 4

- [x] T020 [US4] 在 `src/agentreplayguard/guard.py` 的 `call` 入口增加异步函数检测与可操作错误信息（在任何参数解析与记录写入之前）

**Checkpoint**: US1–US4 均可独立验证。

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: 文档、版本与全量验证。

- [x] T021 [P] 更新 `docs/quickstart.md`：新增异步用法、`acall` 示例、忘记 await 的常见错误说明
- [x] T022 [P] 更新 `README.md`：能力清单加入异步执行支持，路线图勾选 002
- [x] T023 将 `pyproject.toml` 版本提升到 `0.2.0`，并确认版本号与功能范围一致
- [x] T024 运行 `specs/002-async-execution-support/quickstart.md` 全流程：`pytest tests examples/refund`、`ruff check .`、`mypy src/agentreplayguard`、`coverage report --fail-under=90`
- [x] T025 核对 001 同步测试无回归，确认公开 API 无破坏性变更

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖，立即开始
- **Foundational (Phase 2)**: 依赖 Setup，阻塞全部用户故事
- **US1–US4 (Phase 3–6)**: 依赖 Foundational
- **Polish (Phase 7)**: 依赖全部用户故事完成

### User Story Dependencies

- **US1 (P1)**: 仅依赖 Foundational；是异步能力核心
- **US2 (P1)**: 依赖 US1（复用异步工具与 guard）
- **US3 (P2)**: 依赖 US2（复用异步 run 基础设施）
- **US4 (P2)**: 依赖 US1（同步入口检测异步函数）；可与 US3 并行

### Within Each User Story

- 测试先写且失败，再实现
- guard 实现先于 adapter 实现
- 示例在实现完成后补充

### Parallel Opportunities

- T005 与 T006 可并行（不同测试文件）
- T010 与 T011 可并行（单元/集成不同文件）
- T015 与 T016 可并行
- T021 与 T022 可并行

---

## Parallel Example: User Story 1

```bash
# 并行编写异步 guard 测试与契约测试：
Task: "编写 tests/unit/test_guard_async.py"
Task: "扩展 tests/contract/test_public_api.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Setup + Foundational
2. 完成 US1（guard 异步路径 + 示例）
3. **STOP and VALIDATE**: `uv run pytest tests/unit/test_guard_async.py -q`
4. 即得到可用的异步记账能力

### Incremental Delivery

1. Setup + Foundational → 共享辅助就绪
2. + US1 → 异步工具记账与故障注入
3. + US2 → 异步图驱动
4. + US3 → 异步恢复
5. + US4 → 误用保护
6. + Polish → 文档、版本、全量验证

---

## Notes

- [P] 任务 = 不同文件、无依赖；[Story] 标签映射到 spec.md 用户故事
- 每个故事独立可完成、可测试；测试先写并确认失败后再实现
- 每个 Phase 完成后提交一次
- 关键契约（取消语义、同步误用边界、异步与同步一致性）见 contracts 与 research.md，实现不得偏离
- 避免：引入 pytest-asyncio/anyio、实现 astream、引入并发调度、修改 001 同步语义
