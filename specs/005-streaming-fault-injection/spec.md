# Feature Specification: 流式接口的副作用归属与故障注入

**Feature Branch**: `005-streaming-fault-injection`

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: "A 类剩余扩展，从流式接口故障注入（astream/astream_events）开始"

## 背景与问题

`LangGraphAdapter` 目前只提供 `invoke`/`ainvoke`/`resume`/`aresume`/`resume_interrupt`/
`aresume_interrupt`，缺少 `astream` / `astream_events` 流式入口。

当用户用流式方式驱动图（`graph.astream(...)`）时，节点内的 `guard.call` 虽然能正常记账、
注入故障、参与重试（实测见 research R-03），但 effect 的 `run_id` 与 `branch_id` 都是
`None`（research R-02）——因为 `_begin_run`（分配 run_id、设置 thread/checkpoint、注入分支
归属解析器）只在适配器的 `_run`/`_arun` 里调用，直接调图的流式方法不会触发。

后果：effect 成了「无主记录」，`NoDuplicateEffects` 仍能检测重复（去重口径只看
effect_type+business_key），但报告无法回答「哪一次 run、哪个分支产生」，违反宪法第 VIII 条
「失败可解释」。流式是 LangGraph 生产环境的主流消费方式（token 级、chunk 级增量输出），
副作用安全测试必须覆盖它。

本特性在 `LangGraphAdapter` 上新增 `astream` / `astream_events` 入口，让流式执行与
`ainvoke` 一样正确归属 run、thread、checkpoint 与分支。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - astream 流式入口的 effect 归属 (Priority: P1)

用户用 `adapter.astream(...)` 流式驱动图，希望每个 chunk 照常产出，且节点内 effect 的
`run_id` / `branch_id` 正确归属（与 `ainvoke` 一致）。

**Why this priority**: 这是流式支持的基础——归属是后续一切检测的前提，也是本特性的核心
价值（修复 R-02 的「无主记录」）。

**Independent Test**: 一个 `a → b` 串行图（两节点各自 guard 记录 effect），用
`adapter.astream(...)` 遍历完所有 chunk 后，场景报告里两条 effect 的 `run_id` 均为
`run-0001`、`branch_id` 分别为 `a`/`b`。

**Acceptance Scenarios**:

1. **Given** 一个串行图，**When** 用 `adapter.astream(input)` 异步遍历，**Then** 每个 chunk
   按 LangGraph 原样产出，遍历完成后 effect 的 `run_id` 非空、`branch_id` 为产生节点名。
2. **Given** 上述图，**When** 场景 `finish()`，**Then** 报告含一条 `RunSegment`（
   `input_kind=start`、`run_id=run-0001`），与 `ainvoke` 的 RunSegment 结构一致。
3. **Given** 同一个图，**When** 分别用 `ainvoke` 与 `astream` 各跑一遍（各自独立场景、同
   seed），**Then** 两者 effect 记录数、状态序列、attempt、branch_id 一致。

---

### User Story 2 - 流式下的故障注入与重复检测 (Priority: P1)

用户希望流式执行时，lost-ack 等故障注入与 `NoDuplicateEffects` 检测与 `ainvoke` 完全等价。

**Why this priority**: 这是「流式安全测试」的完整闭环——不是只让流式跑起来，而是让流式
下的副作用安全保证与同步/异步路径一致。

**Independent Test**: 一个 lost-ack 场景（`TIMEOUT_AFTER_COMMIT` + retry），用
`adapter.astream(...)` 执行后，`committed_count=2`、`ok=False`，与 `ainvoke` 结论一致。

**Acceptance Scenarios**:

1. **Given** lost-ack 故障 + retry 的退款图，**When** 用 `adapter.astream(...)` 执行，
   **Then** 产生 2 条 committed（attempt 1 带 fault、attempt 2 无 fault），
   `NoDuplicateEffects` 报违规，`ok=False`。
2. **Given** 提交前故障（如 `TIMEOUT_BEFORE_COMMIT`）的图，**When** 用 `astream` 执行，
   **Then** effect 记录为 `not_committed`，函数未执行，故障异常在流式迭代中抛出。
3. **Given** 同一故障场景，**When** 分别用 `ainvoke` 与 `astream` 各跑一遍，**Then** 两者
   `committed_count` 与 `report.ok` 一致。

---

### User Story 3 - astream_events 事件流入口 (Priority: P2)

用户希望用 `adapter.astream_events(...)` 消费事件流（`on_chain_start`/`on_chain_stream`/
`on_chain_end`），同时 effect 归属正确。

**Why this priority**: `astream_events` 是 LangGraph 更细粒度的事件消费方式，覆盖它才算
完整支持流式；但优先级低于 `astream`（chunk 级是最常见消费方式）。

**Independent Test**: 用 `adapter.astream_events(...)` 遍历事件流，事件照常产出，且 effect
的 `run_id`/`branch_id` 正确归属。

**Acceptance Scenarios**:

1. **Given** 一个串行图，**When** 用 `adapter.astream_events(input, version='v2')` 异步遍历，
   **Then** 事件按 LangGraph 原样产出（`on_chain_start`/`on_chain_stream`/`on_chain_end`），
   遍历完成后 effect 归属正确。
2. **Given** 上述图，**When** `finish()`，**Then** RunSegment 结构与 `astream` 一致。

---

### Edge Cases

- **中断（interrupt）图 + 流式**：图带 `interrupt_before` 时，流式会在中断点暂停。
  适配器应在流式结束（或中断）时正确记录 `RunSegment.interrupted`。
- **流式中途异常**：节点抛异常时，`astream` 在迭代中抛出。适配器应正确 `_finish_run`
  （记录 `error_type`），不产生脏状态。
- **空图 / 无 effect**：图无节点调用 guard，流式仍应正常产出 chunk 并记录 RunSegment，
  effect 账本为空。
- **stream_mode 参数透传**：`astream(stream_mode='values'/'updates'/...)` 应透传给底层图，
  归属逻辑与 stream_mode 无关。
- **提前中断遍历**：用户 `break` 提前退出 `async for`，生成器应正确 `_finish_run`（
  GeneratorExit 场景），不留半开 run。

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `LangGraphAdapter` MUST 新增 `astream(input, ...)` 方法，返回异步生成器，逐
  chunk 产出底层图 `astream` 的结果，且透传 `stream_mode` 等参数。
- **FR-002**: `LangGraphAdapter` MUST 新增 `astream_events(input, ...)` 方法，返回异步生成
  器，逐事件产出底层图 `astream_events` 的结果，透传 `version` 等参数。
- **FR-003**: 流式入口 MUST 在开始迭代前执行 `_begin_run`（分配 run_id、设置 thread/
  checkpoint、注入 branch resolver），在生成器耗尽（正常/异常/中断）时执行 `_finish_run`
  （记录 RunSegment），语义与 `ainvoke` 一致。
- **FR-004**: 流式入口下的 effect MUST 携带正确的 `run_id`、`thread_id`、`checkpoint_id`、
  `branch_id`（与 `ainvoke` 一致），修复 R-02 的「无主记录」。
- **FR-005**: 流式入口 MUST 支持异步图（`astream` 要求 `ainvoke` 能力），缺少 `astream`/
  `ainvoke` 能力时抛 `UnsupportedGraphError`（沿用 `_ensure_async_capable` 语义）。
- **FR-006**: 故障注入、重试、`NoDuplicateEffects`/`ConcurrentCommitDetected` 检测在流式
  下 MUST 与 `ainvoke` 等价（复用 EffectGuard/不变量，不新增第二套逻辑）。
- **FR-007**: 流式中途异常 MUST 正确 `_finish_run`（记录 error_type），并原样向迭代者抛出，
  不吞异常、不产生脏 run 状态。
- **FR-008**: 提前退出迭代（`break`/`GeneratorExit`）MUST 正确收尾 run，不留半开 run。
- **FR-009**: 报告（`ScenarioReport.format()`）的 RunSegment 与 effect 归属输出 MUST 保持
  确定性（无 wall clock / 无内存地址）。
- **FR-010**: 既有 `invoke`/`ainvoke`/`resume`/`aresume`/`resume_interrupt`/
  `aresume_interrupt` 的行为 MUST 完全不变（回归）。

### Key Entities

- **流式 RunSegment 归属**：与 `ainvoke` 共享同一 `RunSegment` 结构与 `_begin_run`/
  `_finish_run` 逻辑；仅执行入口（`astream`/`astream_events`）与输出形态（chunk/事件流）不同。
- **无新增数据结构**：复用 `EffectRecord`、`RunSegment`、`ScenarioReport`，不新增字段。

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 一个 `a → b` 串行图用 `adapter.astream(...)` 遍历后，effect 的 `run_id` 为
  `run-0001`、`branch_id` 分别为 `a`/`b`（与 `ainvoke` 一致）。
- **SC-002**: lost-ack 退款图用 `astream` 执行后 `committed_count=2`、`ok=False`，与
  `ainvoke` 结论一致。
- **SC-003**: `astream_events` 事件流遍历后，effect 归属正确，RunSegment 结构与 `astream`
  一致。
- **SC-004**: 流式中途异常与提前退出遍历时，不产生半开 run（RunSegment 正确收尾）。
- **SC-005**: 核心模块覆盖率 ≥90%（宪法第 IV 条）；全量测试断网通过（宪法第 III 条）。
- **SC-006**: 既有 001/002/003/004 全部测试无回归。

---

## Out of Scope

- **同步 `stream` / `stream_events`**：LangGraph 也有同步流式接口，但本工具异步路径已统一
  用 `asyncio.run` 驱动；同步 `stream` 可后续按需补充，不在本阶段（用户可继续用 `invoke`）。
- **流式响应体读取失败语义**（HTTP transport 的流式 chunk 丢失）：属 003 的流式扩展，独立
  特性，不在本阶段。
- **`stream_mode` 下的 token 级断言**：只保证 chunk/事件透传 + effect 归属，不做 chunk 内容
  的业务断言（用户可自行在 `async for` 里断言）。
- **其他框架适配器、其他 HTTP 客户端、本地持久化**：独立特性，见 004 spec 的 Out of Scope。

---

## Assumptions

- LangGraph 受支持版本 1.2.x，`astream`/`astream_events` 均为异步生成器（实测 1.2.20）。
- 流式入口复用既有 `_begin_run`/`_finish_run`/`_ensure_async_capable`，不新增归属机制。
- effect 记账、故障注入、重试、不变量检测均通过节点内 `guard.call` 复用，流式只改变
  执行入口与输出形态。
- 本特性的证据来源为竞品调研（research R-06）与「绕过适配器 astream 导致 effect 无归属」
  的实测事实（R-02）；无真实用户反馈（用户选择由 agent 补调研，宪法第 I 条允许）。
