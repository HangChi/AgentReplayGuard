# Feature Specification: 同步 stream 入口（LangGraphAdapter）

**Feature Branch**: `010-sync-stream`

**Created**: 2026-11-13

**Status**: Implemented

**Input**: User description: "同步 stream/stream_events 入口（005 的同步补充）"

## 背景与问题

005 为 `LangGraphAdapter` 增加了异步 `astream`/`astream_events`，让流式执行能正确归属
run/thread/checkpoint/branch。但同步流式（`stream`）尚未提供——用户在同步上下文中流式驱动
图时，仍需绕过适配器直接调 `graph.stream()`，导致 effect 无归属（同 005 的 research R-02
「绕过适配器导致无主记录」）。

本特性新增同步 `stream()` 入口，与 `astream` 对称，让同步流式执行的 effect 正确归属。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 同步 stream 入口的 effect 归属 (Priority: P1)

用户用 `adapter.stream(...)` 同步流式驱动图，希望 effect 正确归属 run/branch。

**Why this priority**: 这是本特性的唯一能力——补齐同步流式的归属。

**Independent Test**: `a → b` 串行图用 `adapter.stream(...)` 遍历后，effect `run_id=run-0001`、
`branch_id` 分别为 a/b（与 `astream` 一致）。

**Acceptance Scenarios**:

1. **Given** 串行图，**When** 用 `adapter.stream(input)` 遍历，**Then** 每个 chunk 原样产出，
   effect 的 `run_id`/`branch_id` 正确归属。
2. **Given** 上述图，**When** `finish()`，**Then** RunSegment 结构与 `astream` 一致。
3. **Given** 同图分别用 `stream` 与 `astream` 各跑一遍，**Then** effect 记录数、状态序列、
   attempt、branch_id 一致。

---

### Edge Cases

- **节点抛异常**：`stream` 迭代中抛出，`_finish_run` 记录 error_type，异常原样传播。
- **提前 break**：`break` 退出 `for` 循环，`finally` 正常收尾（error_type=None）。
- **参数透传**：`stream(stream_mode=...)` 透传底层图。
- **中断（interrupt）**：含 `__interrupt__` 的 chunk 被累积到 interrupts（同 astream）。

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `LangGraphAdapter` MUST 新增 `stream(input, **kwargs)` 同步生成器，逐 chunk
  产出底层图 `stream` 的结果，透传 `stream_mode` 等参数。
- **FR-002**: `stream()` MUST 在首次迭代前 `_begin_run`，在生成器耗尽（正常/异常/break）时
  `_finish_run`，语义与 `astream` 一致。
- **FR-003**: `stream()` 下的 effect MUST 正确归属 run/thread/checkpoint/branch。
- **FR-004**: `stream()` MUST NOT 要求 `ainvoke` 能力（同步入口，底层用 `invoke` 驱动）。
- **FR-005**: 中途异常 MUST 记录 error_type 并原样抛出；`break` 提前退出 MUST 正常收尾
  （error_type=None）。
- **FR-006**: 既有 `invoke`/`ainvoke`/`astream`/`astream_events`/`resume` 等行为不变（回归）。

### Key Entities

- **无新增数据结构**：复用 `RunSegment`、`EffectRecord`。

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `a → b` 串行图用 `stream()` 遍历后，effect `run_id=run-0001`、`branch_id`
  分别为 a/b（与 `astream` 一致）。
- **SC-002**: 中途异常与提前 break 均正确收尾（不产生半开 run）。
- **SC-003**: 核心模块覆盖率 ≥90%；既有 001–009 测试无回归。

---

## Out of Scope

- **同步 `stream_events`**：v2 不支持、v3 实验性（research R-03），事件流用 `astream_events`
  （005 已提供）。
- **流式响应体丢失**（HTTP 层）：已由 009 覆盖，独立特性。

---

## Assumptions

- LangGraph 1.2.x 的 `stream()` 返回同步 `Iterator`，稳定（实测 1.2.20）。
- 同步 `stream()` 与异步 `astream()` 的 chunk 形态、effect 归属语义一致。
