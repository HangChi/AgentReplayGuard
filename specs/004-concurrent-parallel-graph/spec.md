# Feature Specification: 并发与并行图的副作用竞态与线性一致性检测

**Feature Branch**: `004-concurrent-parallel-graph`

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: "MVP 已完成，把 001/002/003 明确排除的『并发/并行图 + 竞态与线性一致性检测』作为下一阶段实现"

## 背景与问题

当前 `LangGraphAdapter` 通过 `_find_fanout()` 识别图结构中的并行扇出（一个节点有 >1 条
无条件出边），并在 `strict_graph=True`（默认）下直接抛 `UnsupportedGraphError`，拒绝运行。
这意味着任何使用并行分支（fan-out）的图都无法用本工具做副作用安全测试。

而并行分支正是重复副作用的一个**独立来源**：串行图里的重复来自 retry/checkpoint 恢复/
interrupt 重放（001/002 已覆盖），并行图里多分支若各自提交同一业务键，则是另一类重复，
当前工具完全无法检测——因为它连运行都拒绝。

本特性把「拒绝」改为「识别 + 支持 + 检测」，让用户能在并行图上也断言副作用的
exactly-once 与分支归属可解释性。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 允许并行图运行并记录分支归属 (Priority: P1)

用户有一个 fan-out 图（如「下单后并行通知用户 + 扣减库存」），希望用 AgentReplayGuard
在并行图上做副作用安全测试，且报告能指出每个 effect 由哪个分支产生。

**Why this priority**: 这是解锁后续一切检测的前提——当前入口直接拒绝，不做这一步就没有
并行图可用。且「分支归属」是所有并行检测的解释基础。

**Independent Test**: 对一个 `a → (b, c) → END` 的 fan-out 图（b、c 各自调用 guard 记录
不同业务键），`LangGraphAdapter(strict_graph=True)` 不再抛异常，`invoke` 成功，报告中
effect 记录能区分出属于 b 分支还是 c 分支。

**Acceptance Scenarios**:

1. **Given** 一个含 fan-out 的合法图（并行分支写的是带 reducer 的 channel，或写不同
   channel），**When** 用 `strict_graph=True` 的适配器 `invoke`，**Then** 不再抛
   `UnsupportedGraphError`，`invoke` 正常返回。
2. **Given** 上述图的两个分支 b、c 各自通过 `guard.call` 记录一个 effect（不同业务键），
   **When** 场景 `finish()` 生成报告，**Then** 每条 effect 记录携带可区分 b/c 分支的
   归属信息（如 `branch_id`），且归属信息确定性可复现。
3. **Given** 串行图（无 fan-out），**When** 用同一适配器运行，**Then** 行为与 003 完全
   一致，effect 记录的分支归属为单一默认值，不引入任何回归。

---

### User Story 2 - 检测并行分支重复副作用 (Priority: P1)

用户的两个并行分支各自提交了**同一个业务键**（例如并行分支都触发了对同一订单的退款），
希望工具能检测并报告这一「并行重复」。

**Why this priority**: 这是本特性的核心价值——并行维度的 exactly-once。它补上串行检测
（NoDuplicateEffects）在并行来源上的空白。

**Independent Test**: 一个 fan-out 图的两个分支都对同一 `business_key` 提交 effect，场景
注册 `NoDuplicateEffects`，`finish()` 后 `ok=False`，报告指出该 key 被提交 2 次，且能区分
两次提交来自不同分支。

**Acceptance Scenarios**:

1. **Given** fan-out 图，两个分支 b、c 各自 `guard.call(effect_type='refund',
   key='ORDER-1')` 提交同一业务键（无幂等键），**When** 场景注册 `NoDuplicateEffects`
   并 `finish()`，**Then** `ok=False`，报告含 `duplicate_effects` 违规，`actual=2`，
   effect_ids 含两条记录且分支归属不同。
2. **Given** 同一场景但两个分支提交**不同**业务键，**When** `finish()`，**Then** `ok=True`
   （无重复）。
3. **Given** 两个分支提交同一业务键且带**相同幂等键**，**When** `finish()`，**Then**
   按 001 既有去重口径，`committed_count` 为 1，`ok=True`（幂等键正确折叠并行重复）。
4. **Given** 两个分支提交同一业务键且幂等键**相同但参数不同**，**When** `finish()`，
   **Then** 报告含 `parameter_mismatch` 违规（沿用 001 语义）。

---

### User Story 3 - 检测异步交错下的并发提交 (Priority: P3)

用户用异步节点 + await 交错（或手动 `asyncio.gather` 并发调用 guard），使两个副作用调用
在时间上重叠且提交同一业务键，希望工具能判定这是「并发重复」而非「顺序重复」。

**Why this priority**: 这是真正意义上的并发竞态检测，但 LangGraph fan-out 在 1.2.20 是
顺序调度（见 research R-03），故触发面窄、价值低于 US1/US2，作为进阶能力。

**Independent Test**: 手动用 `asyncio.gather` 并发调用两个 `guard.acall`（同一业务键、无
幂等键），场景注册一个「并发提交」不变量，`finish()` 后该不变量报违规，且能定位重叠区间。

**Acceptance Scenarios**:

1. **Given** 两个 `acall` 通过 `asyncio.gather` 并发执行、提交同一业务键（无幂等键），
   **When** 场景注册 `ConcurrentCommitDetected` 不变量并 `finish()`，**Then** 报违规，
   指出两个 effect 的 `started_tick`/`ended_tick` 区间重叠。
2. **Given** 两个 `acall` 顺序执行（`await` 一个再接一个）提交同一业务键，**When**
   `finish()`，**Then** 该不变量不报「并发」违规（区间不重叠），但 `NoDuplicateEffects`
   仍会报重复（两条 committed）。
3. **Given** 两个 `acall` 并发执行但业务键不同，**When** `finish()`，**Then** 不报任何违规。

---

### Edge Cases

- **并行分支写同一无 reducer 的 channel**：LangGraph 会抛 `InvalidUpdateError`，这是状态层
  冲突而非副作用层问题。工具不介入，原样传播（这是用户图设计错误，应在图侧修复）。
- **fan-out 后的 join（分支汇聚）**：汇聚节点后若有副作用，归属应记为「汇聚后」，而非
  某个分支。分支归属仅在 fan-out 区间内有效。
- **嵌套 fan-out**：分支内再 fan-out。归属信息应能表达层级（如 `b.1`、`b.2`），或至少
  保证不同叶子分支的归属唯一。
- **conditional 出边**：`_find_fanout` 目前只统计无条件出边。条件边在同一 superstep 只走
  一条，不构成并行，不应误判为 fan-out（维持现状）。
- **空 fan-out（识别不到并行）**：图实际无并行分支，归属应为默认值，行为完全等价串行。
- **strict_graph=False**：现行为是「跳过 fan-out 检查 + 警告」，本特性后该开关语义需明确
  （见 FR-008）。

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 适配器 MUST 识别图结构中的 fan-out（一个节点有 >1 条无条件出边），并允许其
  运行，不再默认抛 `UnsupportedGraphError`。
- **FR-002**: 系统 MUST 为 fan-out 的每个分支分配一个确定性的 `branch_id`，并在该分支
  执行期间通过上下文把 `branch_id` 注入 `EffectGuard`，写入 `EffectRecord`。
- **FR-003**: `EffectRecord` MUST 新增 `branch_id` 字段（串行图/默认值为空或哨兵值），
  该字段 MUST 确定性可复现（同一 seed/图结构下一致）。
- **FR-004**: `NoDuplicateEffects` 不变量 MUST 在并行重复场景下报告 `duplicate_effects`，
  且报告能指出违规 effect 的分支归属差异（同一业务键来自不同分支）。
- **FR-005**: 系统 MUST 提供一种判定「两个 effect 是否并发」的机制，基于
  `started_tick`/`ended_tick` 区间重叠（异步交错 / 手动并发场景）。
- **FR-006**: 报告（`ScenarioReport` 与 `format()`）MUST 包含 effect 的 `branch_id` 信息，
  且输出保持确定性（无 wall clock、无内存地址）。
- **FR-007**: 核心模块（guard/effects/scenario/invariants/report）MUST 保持不 import
  LangGraph（框架隔离，宪法第 V 条）；分支归属注入由适配器层完成。
- **FR-008**: `strict_graph` 参数的语义 MUST 明确化：`True`（默认）= 识别并支持 fan-out；
  `False` = 关闭 fan-out 相关增强（仅保留警告）。不得再出现「True 拒绝运行」的行为。
- **FR-009**: 同步与异步路径（`invoke`/`ainvoke`）对 fan-out 的 effect 记录数与归属
  分配 MUST 一致（同一 seed 下）。
- **FR-010**: 既有串行图、retry/checkpoint/interrupt 的检测行为 MUST 完全不变（回归）。
- **FR-011**: 并行分支写同一无 reducer channel 导致的 `InvalidUpdateError` MUST 原样传播，
  工具不得吞掉或改写。

### Key Entities

- **BranchContext**: fan-out 区间内的并发上下文，携带确定性 `branch_id`，通过 contextvar
  注入，供 `EffectGuard` 读取。
- **EffectRecord.branch_id**: 扩展字段，记录该 effect 由哪个分支提交；串行场景为空。

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 一个 `a → (b, c) → END` 的 fan-out 图在 `strict_graph=True` 下 `invoke` 成功，
  且连跑 20 次（同 seed）effect 记录与 branch_id 归属完全一致（20/20）。
- **SC-002**: 并行分支提交同一业务键（无幂等键）时，`NoDuplicateEffects` 检测到
  `duplicate_effects` 且 `actual=2`。
- **SC-003**: 同一并行重复场景在有相同幂等键时 `committed_count=1`、`ok=True`。
- **SC-004**: 核心模块（guard/effects/scenario/invariants/report）行覆盖率 ≥90%，与宪法
  第 IV 条一致。
- **SC-005**: 全量测试在断网环境下通过，运行期间无真实外部服务请求（宪法第 III 条）。
- **SC-006**: 新增能力的失败报告可在 2 分钟内让用户指出「哪个 key 被哪些分支重复提交」。
- **SC-007**: 既有 001/002/003 全部测试无回归（串行图行为不变）。

---

## Out of Scope

- **真线程 / 多进程并发**：`threading` / 多进程并发调用 guard 的竞态与线性化，不做（宪法
  第 II 条，真并发不确定，仅提供「异步交错」这一可判定子集，见 US3）。
- **完整并发历史线性化算法**（Wing & Gong 等）：无读操作语义，价值不匹配（见 research R-04）。
- **流式接口**（`astream`/`astream_events`）的并发故障注入：属独立特性，不在本阶段。
- **其他框架适配器**（CrewAI/AutoGen/OpenAI Agents SDK）：独立特性，宪法第 VI 条按需新增。
- **其他 HTTP 客户端适配器**（requests/aiohttp/urllib3）：独立特性。
- **本地持久化 Effect Store**：独立特性。
- **真实外部服务调用/录制、遥测、Web UI、自动修复幂等性**：宪法第 III 条 / 隐私 / 第 VII
  条明确禁止，长期不做。

---

## Assumptions

- LangGraph 受支持版本为 1.2.x（与既有 `[langgraph]` extra 范围一致），fan-out 的同步/异步
  执行顺序均为确定性顺序调度（实测 1.2.20，见 research R-03）。
- 并行分支的 channel 写由用户用 `Annotated` reducer 或不同 channel 保证合法；状态层冲突
  是用户职责，工具不介入。
- 分支归属用 contextvar 注入，基于「fan-out 识别 → 分支确定性编号」实现，不依赖 LangGraph
  内部运行时 API。
- effect 记录仍只落本地内存，默认不上传不联网（宪法第 III 条）。
- 本特性的证据来源为竞品调研（research R-02）与「并行是重复副作用独立来源」的工程事实；
  无真实用户反馈（用户选择由 agent 补竞品调研，宪法第 I 条允许「竞品能力缺口」类证据）。
