# Feature Specification: 异步副作用安全测试

**Feature Branch**: `002-async-execution-support`

**Created**: 2026-11-13

**Status**: Implemented

**Input**: User description: "异步副作用安全测试支持：为 EffectGuard 增加 async effect 装饰器与异步调用路径，为 LangGraphAdapter 增加 ainvoke/aresume/aresume_interrupt，保证故障注入、attempt 计数、effect 记账、报告与同步路径完全一致，并明确拒绝同步误用异步函数（不得静默记为 committed）。"

## 背景与证据

- 已核实事实：现有 `EffectGuard.effect` 的 wrapper 固定为同步函数。当它包裹 `async def`
  工具时，`fn(*args)` 只创建协程对象、不会执行函数体，guard 却按「无异常返回」将其记录为
  `committed`。这会产生一次虚假的已提交记录，属于确定性可复现的正确性缺陷。
- 已核实事实：现有 `LangGraphAdapter` 只调用 `graph.invoke`，不支持异步图执行；异步节点
  （`async def` 节点）在同步驱动下无法被正确测试。
- 合理推断：LangGraph 生产用法中异步工具与 `ainvoke` 占相当比例，若只支持同步路径，用户
  需要为测试改写业务代码，违背「不要求用户改写业务图」的既有契约。
- 证据来源：本仓库 `src/agentreplayguard/guard.py` 与
  `src/agentreplayguard/adapters/langgraph.py` 的现有实现，以及 001 规格中 FR-009、SC-002
  对重试/恢复路径的承诺。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 异步工具被正确记账并注入故障 (Priority: P1)

用户有一个 `async def` 的退款工具（例如基于异步 HTTP 客户端）。他用 guard 包裹该工具，
注入「提交后响应丢失」，图按重试策略再次调用。工具报告同一业务键产生两笔已提交退款，且
每次尝试的序号、状态、参数哈希与同步路径一致。

**Why this priority**: 这是当前实现的直接缺陷：异步工具会被静默记为已提交，导致漏报或
误报。修复它是让工具可用于真实异步项目的首要条件。

**Independent Test**: 运行新增的异步 lost-ack 示例测试，断言账本含 2 条已提交 `refund`
记录且不变量失败；同时断言没有出现「协程对象被当作成功结果」的记录。

**Acceptance Scenarios**:

1. **Given** 一个被 guard 包裹的 `async def` 工具，**When** 等待其正常完成，**Then** 账本
   恰好新增 1 条 `committed` 记录，返回值为工具真实返回值。
2. **Given** 同一异步工具注入「提交后响应丢失」于第 1 次尝试，**When** 调用方重试，**Then**
   账本含 2 条 `committed` 记录，attempt 依次为 1、2，业务键与参数哈希一致。
3. **Given** 异步工具在提交前抛业务异常，**When** 调用方捕获异常，**Then** 账本记录
   `not_committed` 且不产生任何 `committed` 记录。

---

### User Story 2 - 异步驱动 LangGraph 图 (Priority: P1)

用户的图包含 `async def` 节点与异步工具。他用适配器的异步入口首次执行图，并在配置了
RetryPolicy 的节点上触发 lost-ack；工具能按 run/thread/checkpoint 归属记录并给出重复结论。

**Why this priority**: 异步节点在同步驱动下无法执行；不提供异步驱动，US1 的价值无法延伸到
真实图。

**Independent Test**: 运行新增的异步集成测试，断言重复副作用被检测、报告中的 run 片段与
同步驱动同结构。

**Acceptance Scenarios**:

1. **Given** 一个含异步节点的串行图，**When** 通过异步入口执行，**Then** 返回结果与 run
   片段被记录，effect 归属到当前 thread 与 checkpoint。
2. **Given** 同一 lost-ack 故障计划，**When** 分别用同步与异步入口执行等价图，**Then**
   两者 effect 数量、状态序列与 attempt 序号一致。

---

### User Story 3 - 异步恢复：Checkpoint 与 Interrupt (Priority: P2)

用户在异步图中使用 checkpointer；进程中断后从 checkpoint 恢复，或在 interrupt 后恢复。
工具按既有规则区分「已完成副作用不重复」与「节点整体重跑导致重复」。

**Why this priority**: 恢复路径是产品核心承诺之一，异步模式必须与同步模式行为一致，否则
异步用户会得到不可信结论。

**Independent Test**: 运行新增的异步 resume 与 interrupt 集成测试，断言恢复后的提交计数
与同步路径结论一致。

**Acceptance Scenarios**:

1. **Given** 副作用已完成并写入 checkpoint，**When** 异步恢复，**Then** 不新增 `committed`
   记录。
2. **Given** 副作用位于 checkpoint 之前，**When** 异步恢复，**Then** 新增 `committed`
   记录且被不变量检测为重复。
3. **Given** 图在 interrupt 处暂停，**When** 通过异步 interrupt 恢复入口恢复，**Then**
   若副作用在 interrupt 之前则重复被检测，之后则不重复。

---

### User Story 4 - 误用被明确拒绝 (Priority: P2)

用户把异步工具交给了同步调用入口（例如复用旧的同步调用路径或同步驱动路径）。工具立即
给出明确错误，说明应使用异步调用方式，而不是静默记录为已提交。

**Why this priority**: 静默误记会让测试「假通过」，比报错危险得多；这是异步支持必须关闭的
安全缺口。

**Independent Test**: 单元测试断言同步调用异步工具时抛出配置错误，且账本没有任何
`committed` 记录。

**Acceptance Scenarios**:

1. **Given** guard 装饰的 `async def` 工具，**When** 通过同步调用入口执行，**Then** 立即
   抛出配置错误，错误信息包含正确用法提示，账本无新增记录。
2. **Given** 同步工具，**When** 使用异步调用入口，**Then** 允许正常执行并返回结果（不强制
   用户区分同步/异步入口）。

---

### Edge Cases

- **协程被取消**：异步工具在执行中被取消（如外部超时触发取消），必须记录为「结果未知」而
  非「已提交」，并向上传播取消。
- **忘记 await**：直接调用异步 wrapper 而不等待，属于语言级协程语义，工具不拦截；文档需
  给出正确用法与常见错误示例。
- **异步工具返回协程/生成器**：返回值不得被当作已提交的证据；记账只依据函数是否正常完成。
- **同一业务键并发调用**：本次特性不支持并发语义，遇到并行扇出仍按既有规则快速失败。
- **异步图中混用同步节点**：必须正常工作，不得要求整图异步化。
- **未声明不变量**：与同步路径一致，场景结束给出明确警告。
- **无 checkpointer 时异步恢复**：与同步路径一致，快速失败并说明原因。
- **异步故障注入不得使用真实延迟或真实网络**：时间推进仍由逻辑时钟驱动。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 用户 MUST 能用同一个 `effect` 声明同时包裹同步与异步工具，无需为异步工具
  编写不同的场景配置。
- **FR-002**: 异步工具的每次尝试 MUST 被记录为独立的 effect 记录，包含与同步路径相同的
  字段：effect 类型、业务键、参数哈希、幂等键哈希、attempt、提交状态、run/thread/checkpoint
  归属与逻辑时间。
- **FR-003**: 异步工具的故障注入 MUST 与同步路径语义一致：提交前故障记录 `not_committed`
  并抛出；提交后故障记录 `committed` 并抛出；参数哈希与业务键必须相同。
- **FR-004**: 异步工具抛出的业务异常 MUST 记录 `not_committed` 并原样传播，不得被包装或
  吞掉。
- **FR-005**: 异步工具被取消时 MUST 记录「结果未知」状态并传播取消，不得记录为已提交。
- **FR-006**: 系统 MUST 在通过同步调用入口执行异步工具时立即失败，错误信息 MUST 说明应
  使用异步调用方式；失败时 MUST NOT 新增任何 effect 记录。直接调用异步 wrapper 但忘记
  `await` 属于语言级协程语义，不在拦截范围，文档 MUST 明确正确用法。
- **FR-007**: 系统 MUST 允许用异步调用入口执行同步工具，并返回其正常结果。
- **FR-008**: 适配器 MUST 提供异步首次执行入口，行为与同步入口一致：记录 run 片段、归属
  effect、提取 interrupt、传播图异常。
- **FR-009**: 适配器 MUST 提供异步 checkpoint 恢复入口，且仅在前次运行存在时允许恢复；
  无 checkpointer 时 MUST 快速失败并说明原因。
- **FR-010**: 适配器 MUST 提供异步 interrupt 恢复入口，且仅在前次运行处于中断状态时允许
  恢复。
- **FR-011**: 同一 seed、同一故障计划下，同步与异步路径 MUST 产生相同数量的 effect 记录、
  相同状态序列与相同 attempt 序号。
- **FR-012**: 异步示例与测试 MUST 在无网络环境下运行，MUST NOT 引入真实延迟、真实网络请求
  或新增运行时依赖。
- **FR-013**: 异步路径 MUST 复用现有报告结构，用户无需学习第二套报告格式。
- **FR-014**: 现有同步公开 API MUST 保持向后兼容；不得要求现有用户修改场景声明。
- **FR-015**: 异步不支持并行扇出时 MUST 与同步路径一致地快速失败，并说明支持范围。

### Key Entities

- **异步 Effect 尝试**：与同步 effect 记录同构，复用既有记录与去重口径，不引入新实体。
- **异步 Run 片段**：与同步 run 片段同构，复用既有 run/thread/checkpoint 归属结构。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 异步 lost-ack 场景能在 100% 的运行中检测出同一业务键的 2 条已提交记录并使
  测试失败。
- **SC-002**: 同一 seed 下，同步与异步等价场景的 effect 记录数、状态序列与 attempt 序号
  20/20 次完全一致。
- **SC-003**: 同步误用异步工具时 100% 抛出明确错误，且账本中已提交记录数为 0。
- **SC-004**: 异步 checkpoint 恢复与 interrupt 恢复的结论与同步路径一致，样例覆盖「重复」
  与「不重复」两种结果。
- **SC-005**: 全部异步测试在断网环境下通过，单个典型异步场景完成时间小于 5 秒。
- **SC-006**: 核心模块行覆盖率保持不低于 90%，ruff 与类型检查无错误。
- **SC-007**: 现有同步测试全部通过，公开 API 无破坏性变更。

## Out of Scope

- 并发异步任务、并行图、后台任务的竞态与线性一致性检测。
- 流式执行接口（`astream` / `astream_events`）的故障注入与断言。
- 异步测试运行器依赖（如 pytest-asyncio / anyio）的引入；示例使用标准库事件循环运行。
- 异步 HTTP 客户端或真实网络服务的接入。
- 其他框架适配器。

## Assumptions

- 用户使用的 LangGraph 版本支持异步执行入口（与现有可选依赖版本范围一致）。
- 用户已有能力在异步测试中驱动协程（如自行使用 pytest-asyncio 或 anyio），本特性不改变
  其测试入口选择。
- 异步执行仍是单线程事件循环内的确定性顺序执行；不引入并发调度带来的不确定性。
- 取消场景的「结果未知」语义与既有 `unknown` 状态一致，不新增状态值。
- 异步与同步路径共享同一 Effect Store、故障注入器与不变量，不引入第二套账本。
