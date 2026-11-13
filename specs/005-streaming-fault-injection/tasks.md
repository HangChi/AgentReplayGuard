---
description: "Task list for 005 streaming fault injection"
---

# Tasks: 流式接口的副作用归属与故障注入

**Input**: Design documents from `/specs/005-streaming-fault-injection/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: 测试先行是强制要求（宪法第 IV 条）。

**Organization**: 按用户故事分组。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件，无依赖）
- **[Story]**: 所属用户故事（US1–US3）

---

## Phase 0: 前置与基线（Setup）

- [ ] T001 将 `pyproject.toml` 版本提升到 `0.5.0`
- [ ] T002 运行基线：`pytest -q`、`ruff check .`、`mypy src/agentreplayguard`、`coverage
  --fail-under=90`，记录全绿

---

## Phase 1: User Story 1 — astream 流式入口的 effect 归属 (Priority: P1) 🎯

**Goal**: `adapter.astream` 流式驱动图，effect 正确归属 run/branch。

**Independent Test**: `a → b` 串行图用 `astream` 遍历后，effect `run_id=run-0001`、
`branch_id` 分别为 a/b。

### Tests for US1 ⚠️

- [ ] T003 [P] [US1] 编写 `tests/integration/test_streaming.py`：`astream` 遍历产出 chunk；
  effect `run_id`/`branch_id` 正确；`finish()` 后 RunSegment 结构正确；`ainvoke` vs `astream`
  结论一致；缺 `ainvoke` 抛 `UnsupportedGraphError`
- [ ] T004 [P] [US1] 编写 `tests/unit/test_adapter_stream.py`：用假 graph stub 验证
  `_begin_run`/`_finish_run` 在生成器生命周期正确调用（含提前 break 收尾）

### Implementation for US1

- [ ] T005 [US1] 在 `adapters/langgraph.py` 新增 `astream` 异步生成器：`_ensure_async_capable`
  → `_begin_run` → 逐 chunk 透传 → `finally _finish_run`

---

## Phase 2: User Story 2 — 流式故障注入与重复检测 (Priority: P1) 🎯

**Goal**: lost-ack 等故障注入与 NoDuplicateEffects 在流式下与 ainvoke 等价。

**Independent Test**: lost-ack + retry 图用 `astream` 执行后 `committed_count=2`、`ok=False`。

### Tests for US2 ⚠️

- [ ] T006 [P] [US2] 扩展 `tests/integration/test_streaming.py`：lost-ack + retry 流式
  `committed_count=2`、`ok=False`；提交前故障 `not_committed` 且异常抛出；`ainvoke` vs
  `astream` 结论一致

### Implementation for US2

- [ ] T007 [US2] 确认无需新增逻辑（复用 guard.call + 不变量），仅在流式遍历时累积 interrupts
  传给 `_finish_run`

---

## Phase 3: User Story 3 — astream_events 事件流入口 (Priority: P2)

**Goal**: `adapter.astream_events` 消费事件流，effect 归属正确。

**Independent Test**: `astream_events(version='v2')` 遍历后事件产出、effect 归属正确。

### Tests for US3 ⚠️

- [ ] T008 [P] [US3] 扩展 `tests/integration/test_streaming.py`：`astream_events` 遍历产出
  事件（on_chain_start/stream/end）；effect 归属正确；RunSegment 结构与 astream 一致

### Implementation for US3

- [ ] T009 [US3] 在 `adapters/langgraph.py` 新增 `astream_events` 异步生成器，结构与
  `astream` 相同，透传 `version` 参数

---

## Phase 4: 文档与示例（Docs & Examples）

- [ ] T010 [P] 新增 `examples/refund/test_refund_streaming.py`：流式退款示例（含 lost-ack
  检测）
- [ ] T011 [P] 更新 `docs/quickstart.md`：新增流式用法与注意事项
- [ ] T012 [P] 更新 `README.md`：能力清单加入流式支持，路线图勾选 005

---

## Phase 5: 全量验证（Verification）

- [ ] T013 运行 `specs/005-streaming-fault-injection/quickstart.md` 全流程：`pytest tests
  examples/refund`、`ruff check .`、`mypy src/agentreplayguard`、`coverage report
  --fail-under=90`
- [ ] T014 核对 001/002/003/004 无回归，确认公开 API 无破坏性变更（仅新增 2 方法）

---

## Notes（贯穿全清单的硬约束）

- **归属生命周期**：`astream`/`astream_events` 的 `_begin_run`/`_finish_run` 必须用 `finally`
  包裹，保证正常耗尽、异常、break 三条退出路径都收尾。
- **框架隔离**：改动只在 `adapters/langgraph.py`；核心模块不 import LangGraph。
- **无新依赖、无新字段**：复用 EffectRecord/RunSegment/不变量，不新增结构。
- **参数透传**：`stream_mode`/`version` 等必须透传底层图，归属逻辑与参数无关。
