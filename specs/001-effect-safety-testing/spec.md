# Feature Specification: AgentReplayGuard MVP — LangGraph 副作用安全测试

**Feature Branch**: `001-effect-safety-testing`

**Created**: 2026-11-12

**Status**: Implemented

**Input**: MVP：面向 LangGraph + pytest 的 agent 副作用安全测试工具。提供 Effect Store、
Fault Injector、Simulated Service、Invariant Checker、LangGraph Adapter。MVP 仅覆盖串行
图，交付退款示例与快速开始文档。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 复现「提交后响应丢失」导致的重复退款 (Priority: P1)

一名使用 LangGraph 构建退款流程的 Python 工程师，怀疑重试会造成重复退款。他在 pytest
中用模拟退款服务替换真实服务，声明「第一次调用在服务端提交成功、但响应丢失」的故障计划，
然后运行图。工具记录每一次副作用尝试，并在检测到同一业务操作被提交两次时让测试失败，
同时给出可定位的报告。

**Why this priority**: 这是项目的核心价值与最小可行闭环——用户在一小时内就能复现自己最
担心的线上事故。没有这条，其它功能都没有意义。

**Independent Test**: 单独运行退款示例中的 lost-ack 场景，测试失败并输出重复副作用报告；
不依赖自定义不变量或 interrupt 能力。

**Acceptance Scenarios**:

1. **Given** 退款工具未使用幂等键，**When** 第一次调用在提交后退回超时、图按重试策略再次调用，
   **Then** 测试失败，报告明确指出同一业务键发生了两次已提交的退款。
2. **Given** 上述场景，**When** 查看失败报告，**Then** 报告包含 effect 类型、业务键、每次尝试的
   序号与提交状态、参数哈希、所属 run/thread/checkpoint，以及使用的 seed。
3. **Given** 同一场景配置与 seed，**When** 重复运行，**Then** 每次得到相同的 effect 计数与相同结论。

---

### User Story 2 - 验证幂等键确实消除了重复副作用 (Priority: P1)

同一名工程师为退款工具加上幂等键，希望确认修复有效。他用同一故障计划重跑场景，工具显示
只有一笔退款被提交，所有不变量通过；当他故意让每次重试生成不同的幂等键时，测试再次失败。

**Why this priority**: 工具必须同时支持「发现缺陷」和「验证修复」，否则用户无法用它形成闭环。

**Independent Test**: 在退款示例中开启幂等键，重跑 lost-ack 场景；测试通过且账本只有一笔退款。

**Acceptance Scenarios**:

1. **Given** 退款请求携带相同幂等键，**When** 发生提交后响应丢失并重试，**Then** 模拟账本只有一笔
   退款，测试通过。
2. **Given** 每次重试生成了不同的幂等键（错误实现），**When** 重跑同一场景，**Then** 测试失败，
   报告指出重复提交且幂等键不一致。

---

### User Story 3 - 验证 Checkpoint 恢复不会重复执行已完成的副作用 (Priority: P1)

工程师的图在退款完成后、流程收尾前被中断（进程崩溃或人工停止）。他从 checkpoint 恢复运行，
想确认恢复不会再次退款。工具应能驱动恢复过程，并按 run/thread/checkpoint 归属展示 effect。

**Why this priority**: Checkpoint 恢复是 LangGraph 的核心能力，也是重复副作用最隐蔽的来源之一；
它是本项目区别于普通 mock 工具的关键场景。

**Independent Test**: 在退款示例中模拟提交后中断并从 checkpoint 恢复，断言已提交的 effect 不再增加。

**Acceptance Scenarios**:

1. **Given** effect 已提交且 checkpoint 位于该 effect 之后，**When** 从 checkpoint 恢复，**Then** 不产生
   新的已提交 effect，测试通过。
2. **Given** checkpoint 位于 effect 所在节点执行之前（节点被整体重跑），**When** 恢复或重试，
   **Then** 工具检测到重复提交并让测试失败。
3. **Given** 一次场景中发生多次恢复，**When** 查看报告，**Then** 每次 effect 都能归属到对应
   run/thread/checkpoint。

---

### User Story 4 - 验证 Interrupt 恢复后的重放安全性 (Priority: P2)

图在退款前通过 interrupt 暂停等待人工确认。工程师恢复执行后发现节点从头重跑，担心 effect
被重复执行。工具应能复现该路径，并明确区分「effect 在 interrupt 之前」与「effect 在 interrupt
之后」两种放置方式的结论。

**Why this priority**: 官方文档已说明 interrupt 会重跑节点，但用户缺少低成本验证手段；它补齐
LangGraph 主要恢复路径。

**Independent Test**: 两个示例场景分别把退款放在 interrupt 前/后，恢复后断言 effect 计数。

**Acceptance Scenarios**:

1. **Given** 退款在 interrupt 之前已提交，**When** 用户恢复并重跑节点，**Then** 工具检测到重复提交。
2. **Given** 退款只在 interrupt 之后执行一次，**When** 恢复运行，**Then** 只有一笔退款，测试通过。

---

### User Story 5 - 用业务不变量描述「应该发生什么」 (Priority: P2)

工程师不想只依赖重复检测，还想声明「整个场景中退款最多 1 笔」「通知最多 1 次」或自定义
业务规则。他用内置不变量和自定义断言表达这些期望，失败时得到包含期望值与实际值的报告。

**Why this priority**: 不同业务的正确性定义不同，固定规则无法覆盖；但不变量是锦上添花，可在
核心闭环之后交付。

**Independent Test**: 编写一个包含 `max_effect_count` 与自定义 predicate 的场景，分别构造通过和
失败用例。

**Acceptance Scenarios**:

1. **Given** 场景声明退款最多 1 笔，**When** 实际发生 2 笔，**Then** 测试失败并显示期望 1、实际 2。
2. **Given** 自定义业务断言返回不满足，**When** 场景结束，**Then** 报告包含断言名称、相关 effect
   与失败原因。
3. **Given** 所有不变量满足，**When** 场景结束，**Then** 测试通过并可输出 effect 摘要。

---

### User Story 6 - 在 CI 中稳定、快速地回归 (Priority: P3)

工程师把场景测试加入 CI，希望不依赖网络、不依赖外部服务，且每次结论一致。同一场景重复运行
20 次结果不变，单个场景在数秒内完成。

**Why this priority**: CI 集成决定工具能否长期使用，但它依赖前五条 story 的能力，优先级最低。

**Independent Test**: 在断网环境连续运行 20 次退款场景，比较结论与耗时。

**Acceptance Scenarios**:

1. **Given** 运行环境无网络，**When** 执行全部场景测试，**Then** 结论与本地一致且无外部调用。
2. **Given** 同一场景与 seed，**When** 连续运行 20 次，**Then** 测试结论与 effect 计数完全一致。
3. **Given** 单个典型场景，**When** 执行，**Then** 完成时间小于 5 秒。

---

### Edge Cases

- **部分成功**：一次业务操作中扣款成功但通知失败时，两个 effect 必须分别记录与断言，不能合并
  为一次成功或一次失败。
- **相同业务键、不同参数**：必须视为潜在冲突，报告需突出参数哈希不一致，而不是静默去重。
- **effect 之前失败**：图在调用副作用前抛错时，不得产生任何「已提交」记录。
- **业务拒绝（4xx）**：模拟服务返回业务错误时不得按可重试故障处理，不得触发自动重试。
- **多次重试但仅一次提交**：不得误报重复。
- **跨测试隔离**：同一测试会话中多个场景的 effect、账本与 checkpoint 必须互不污染。
- **未显式配置 seed**：使用并记录一个固定默认 seed，保证仍可复现。
- **未声明任何不变量**：场景结束时应给出明确警告，避免用户误以为「通过」代表安全。
- **不支持的图形态**（并行分支、异步节点等）：必须快速失败并给出清晰说明，而不是给出不可信结论。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 用户 MUST 能用一个场景声明描述：被测图入口、模拟服务、故障计划、seed、幂等键
  开关与业务不变量，并在 pytest 中一行启用。
- **FR-002**: Effect Store MUST 记录每次副作用尝试：effect 类型、业务键、参数哈希、尝试序号、
  提交状态（未提交/已提交/结果未知）、所属 run/thread/checkpoint 标识与逻辑时间。
- **FR-003**: Effect Store MUST 提供按 effect 类型、业务键、run/thread 查询与计数的能力，供测试
  断言与报告使用。
- **FR-004**: Fault Injector MUST 支持至少五类故障：提交前超时、提交后响应丢失、连接重置、
  服务端 500、部分成功。
- **FR-005**: 故障 MUST 由 seed 与故障计划确定；相同场景与 seed MUST 产生相同执行轨迹。
- **FR-006**: 工具 MUST 提供退款模拟服务，包含内存账本，支持开启/关闭幂等键，并可按幂等键
  查询已提交退款。
- **FR-007**: Invariant Checker MUST 内置「无重复 effect」与「effect 数量上限」两类不变量，并支持
  用户自定义断言函数。
- **FR-008**: 不变量失败时 MUST 输出可定位报告：effect 类型、业务键、参数哈希、尝试序号、提交
  状态、run/thread/checkpoint、期望值与实际值。
- **FR-009**: LangGraph Adapter MUST 能驱动图的首次执行、按重试策略重试、从 checkpoint 恢复、
  以及在 interrupt 后恢复，且 MUST NOT 要求用户改写业务图。
- **FR-010**: 适配层 MUST 在每次执行后提供本次 run 的 effect 记录与检查结论，供 pytest 断言。
- **FR-011**: 每个场景 MUST 使用隔离的 Effect Store、模拟服务与 checkpoint 状态，测试间不得串扰。
- **FR-012**: 工具 MUST 在无网络环境下完整运行，且 MUST NOT 发起任何真实外部服务调用。
- **FR-013**: 当场景未声明任何不变量时，工具 MUST 给出明确警告。
- **FR-014**: 当检测到不支持的图形态或调用方式时，工具 MUST 立即失败并说明原因与支持范围。
- **FR-015**: 项目 MUST 提供可运行的退款示例与快速开始文档，使新用户在 10 分钟内完成首次运行。
- **FR-016**: 工具 MUST 暴露复现信息（场景配置摘要、seed、失败报告），使用户能原样重跑并得到
  相同结论。

### Key Entities *(include if feature involves data)*

- **Scenario（场景）**：一次可复现实验的完整声明，包含被测图、模拟服务配置、故障计划、seed、
  幂等键开关与不变量集合。
- **Effect Record（副作用记录）**：一次副作用尝试的事实记录，包含类型、业务键、参数哈希、尝试
  序号、提交状态、归属标识（run/thread/checkpoint）与逻辑时间。
- **Fault Plan（故障计划）**：按调用次序或条件描述在何处注入何种故障的规则集合。
- **Simulated Ledger（模拟账本）**：模拟服务中已提交业务操作的事实集合；退款示例中即退款流水。
- **Invariant（不变量）**：对场景结果应满足性质的声明，可为内置规则或自定义断言。
- **Run Evidence（运行证据）**：一次场景执行后的报告，包含 effect 时间线、各不变量结论、seed 与
  场景摘要。
- **Checkpoint Reference（检查点引用）**：用于恢复执行的 LangGraph 检查点标识，与 run/thread
  关联。

## Out of Scope (MVP)

以下内容明确不在 MVP 范围，避免范围蔓延：

- LLM 输出质量评估、提示词评测、数据集回归。
- LangGraph 之外的 Agent 框架适配（CrewAI、AutoGen、OpenAI Agents SDK 等）。
- 生产环境监控、遥测、告警或流量录制回放。
- Web UI、云控制面、托管服务。
- 自动修复幂等性、自动生成幂等键或自动改写用户代码。
- 并发/异步图之间的竞态与线性一致性检测（MVP 仅覆盖串行图）。
- 跨进程持久化、分布式 Effect Store。
- 真实支付、退款、邮件、数据库等外部服务的调用或录制。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 新用户按快速开始操作，可在 10 分钟内完成安装、运行退款示例并看到一次失败报告。
- **SC-002**: 对「重试、checkpoint 恢复、interrupt 恢复、提交后响应丢失」四类路径中的至少三类，
  工具能稳定复现重复副作用并使测试失败。
- **SC-003**: 同一 lost-ack 场景下，无幂等键时测试失败、有幂等键时测试通过，两个结论在报告中
  清晰可辨。
- **SC-004**: 同一场景与 seed 连续运行 20 次，测试结论与 effect 计数 20/20 一致。
- **SC-005**: 单个典型场景在本地无网络环境下的执行时间小于 5 秒。
- **SC-006**: 3 名目标用户在仅阅读失败报告的情况下，能在 2 分钟内指出重复发生的 effect 及其
  业务键（可用性验证）。
- **SC-007**: 核心模块（Effect Store、Fault Injector、Invariant Checker、LangGraph Adapter）行
  覆盖率不低于 90%。
- **SC-008**: 全部测试在断网环境下通过，运行期间无任何真实外部服务请求。

## Assumptions

- 目标用户使用 Python 3.10+、pytest，并已能用 LangGraph 构建串行工作流。
- MVP 只支持串行图与单线程执行；LangGraph 受支持版本范围在技术计划阶段锁定。
- 用户能够为每个副作用定义稳定的业务键（如退款单号），这是重复检测的前提。
- MVP 使用内存存储即可满足单次测试运行；跨进程持久化不是首版需求。
- 模拟服务以项目内置的退款服务为参考实现，用户可仿照它接入自己的外部服务模拟。
- 已核实的 LangGraph 行为（durability 不保证外部副作用 exactly-once、interrupt 重跑节点）
  作为设计前提；具体 API 细节在技术计划阶段对照官方文档确认。
- Phase 0 计划中的故障复现脚本、竞品 hands-on 与用户访谈尚未执行，相关结论仍需验证，不阻塞
  本规格进入技术计划，但必须在发布前补做。
