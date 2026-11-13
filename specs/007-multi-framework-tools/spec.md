# Feature Specification: 多框架工具副作用记账

**Feature Branch**: `007-multi-framework-tools`

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: "A 类剩余扩展，其他 Agent 框架适配器（OpenAI Agents SDK / CrewAI / AutoGen）"

## 背景与问题

AgentReplayGuard 目前只对 LangGraph 提供深度适配（图执行 + run/checkpoint/branch 归属），
对 `httpx`/`requests` 提供 HTTP 传输层适配。但 OpenAI Agents SDK、CrewAI、AutoGen 也是广泛
使用的 Agent 框架，其工具（副作用函数）目前无法接入本工具的记账与故障注入。

关键事实（research R-01）：这些框架的工具函数**本质都是普通 Python callable**，副作用发生
在「工具函数被调用的那一刻」，与本工具 `guard.effect()` 的拦截点完全一致。因此不需要像
LangGraph 那样写完整适配器（驱动整图），只需「用 `guard.effect()` 装饰工具函数」即可复用
全部现有能力（attempt 记账、参数哈希、五类故障注入、`NoDuplicateEffects` 等不变量）。

本特性交付：① 一个框架无关的「工具函数接入」文档与契约；② OpenAI Agents SDK 的可运行
scripted 示例（官方离线测试设施最成熟，research R-02）；③ CrewAI / AutoGen 的接入说明。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 用 guard.effect 装饰任意框架工具函数 (Priority: P1)

用户有一个 OpenAI Agents SDK / CrewAI / AutoGen 的工具函数，希望用 `guard.effect()` 装饰后
自动记账、注入故障、参与重复检测，无需改动框架运行时。

**Why this priority**: 这是本特性的核心——证明「工具函数级接入」对多框架通用，是本特性的
价值锚点。

**Independent Test**: 一个被 `@guard.effect(...)` 装饰的普通 callable（模拟任意框架工具），
直接调用后 effect 正确记账，故障注入与不变量检测正常。

**Acceptance Scenarios**:

1. **Given** 一个 `@scenario.guard().effect("refund", key="refund_id")` 装饰的同步函数，
   **When** 直接调用，**Then** effect 记录 1 条 committed，业务键正确。
2. **Given** 一个 `@scenario.guard().effect(...)` 装饰的异步函数，**When** `await` 调用，
   **Then** effect 记录 1 条 committed（异步路径，见 002）。
3. **Given** 注入 lost-ack 故障 + 业务侧重试，**When** 两次调用，**Then** `NoDuplicateEffects`
   检测到 2 条 committed；有幂等键折叠为 1。

---

### User Story 2 - OpenAI Agents SDK scripted 工具流程 (Priority: P1)

用户用 OpenAI Agents SDK 的官方 `ScriptedModel` 离线跑一个工具流程，希望工具函数的副作用
被正确记账。

**Why this priority**: OpenAI Agents SDK 是三者中离线确定性测试最成熟的，scripted 示例能
证明「本工具可接入真实框架工具管线」。

**Independent Test**: 用 `ScriptedModel` 脚本化一个 `function_call → 工具执行 → 最终答复`
流程，工具函数被 `guard.effect()` 装饰，跑完后 effect 正确记账。

**Acceptance Scenarios**:

1. **Given** 一个 `@tool` 装饰且内部用 `guard.effect()` 包裹副作用（或直接 `@guard.effect`
   + `@tool` 组合）的工具，**When** 用 `ScriptedModel` 脚本化 `function_call` 跑 `Runner.run`，
   **Then** effect 记录 1 条 committed，工具正常返回。
2. **Given** 注入 `TIMEOUT_AFTER_COMMIT` 故障到该工具，**When** scripted run 执行，
   **Then** effect 记录 committed（提交后故障），异常按故障语义抛出。

---

### User Story 3 - CrewAI / AutoGen 接入文档 (Priority: P2)

用户希望知道如何把 guard 接入 CrewAI / AutoGen 工具函数。

**Why this priority**: 这两个框架的工具函数同样是普通 callable，接入方式与 US1 一致，主要
是提供文档与示例，价值低于可运行的 scripted 示例（US2）。

**Independent Test**: 文档明确说明「用 `guard.effect()` 装饰工具函数即可」，并提供最小代码
片段。

**Acceptance Scenarios**:

1. **Given** CrewAI 的 `@tool` 函数，**When** 按文档用 `guard.effect()` 装饰，**Then** 工具
   函数直接调用时 effect 正确记账（无需 Agent/LLM）。
2. **Given** AutoGen 的工具函数，**When** 按文档接入，**Then** 同上。

---

### User Story 4 - 真实 LLM 集成演示 (Priority: P3，不进 CI)

用户有一个真实的 LLM 端点，希望**手动**跑一个演示，验证带 guard 的工具在真实 agent 下能
抓到重复副作用。

**Why this priority**: 这是「能力验证」而非「确定性测试」。真实 LLM 天生不可复现（同 seed
下模型可能调用不同工具），违反宪法第 II 条的确定性，故**不进 CI、不写死 key**，仅作手动
演示脚本，证明「guard 在真实框架运行时下有效」。

**Independent Test**: 手动设置环境变量后运行演示脚本，真实 agent 调用带 guard 的退款工具，
注入 lost-ack 后 `NoDuplicateEffects` 抓到重复。

**Acceptance Scenarios**:

1. **Given** 环境变量提供 `OPENAI_BASE_URL` 与 `OPENAI_API_KEY`，**When** 运行演示脚本，
   **Then** 真实 agent 调用工具，effect 被记账，注入故障后重复副作用被检测。
2. **Given** 未提供环境变量，**When** 运行演示脚本，**Then** 脚本跳过并提示（不报错）。

---

### Edge Cases

- **装饰器顺序**：`@tool` 与 `@guard.effect` 的叠加顺序（谁在外层）影响函数签名保留与工具
  schema 生成，需在文档明确推荐顺序。
- **工具函数签名丢失**：`guard.effect` 用 `functools.wraps` 保留签名；与框架装饰器叠加时需
  验证签名/描述仍可被框架识别。
- **异步工具**：OpenAI Agents SDK 支持 async 工具，`guard.effect` 会自动识别 `async def`（002）。

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 复用现有 `EffectGuard.effect` 装饰器完成工具函数级副作用记账，不新增框架专属
  运行时逻辑。
- **FR-002**: 文档（`docs/quickstart.md` 新增章节 + 本 spec 的 quickstart）MUST 说明「用
  `guard.effect()` 装饰工具函数」的多框架通用接入方式，并明确装饰器叠加顺序。
- **FR-003**: 提供 OpenAI Agents SDK 的 scripted 可运行示例（`examples/` 下），使用官方
  `ScriptedModel` 离线跑工具流程，验证 effect 记账。
- **FR-004**: 提供 CrewAI / AutoGen 的接入说明（工具函数直接调用 + guard 装饰），不提供
  Agent 级完整示例（AutoGen 无官方离线设施，CrewAI 需 mock LLM，见 research R-03/R-04）。
- **FR-005**: 新增示例不引入真实 LLM API 调用，全部离线（宪法第 III 条）。
- **FR-006**: 核心包与既有 LangGraph/httpx/requests 适配器行为不变。
- **FR-007**: 提供真实 LLM 集成**演示脚本**（非测试、不进 CI），通过环境变量
  `OPENAI_BASE_URL`/`OPENAI_API_KEY` 注入端点与密钥，未提供时跳过；脚本 MUST NOT 硬编码
  任何密钥。

### Key Entities

- **无新增数据结构**：复用 `EffectGuard`/`EffectRecord`/不变量。

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 一个 `guard.effect()` 装饰的 callable 直接调用后 effect 正确记账（同步+异步）。
- **SC-002**: OpenAI Agents SDK scripted 工具流程跑完后 effect 正确记账，且全程无真实 LLM 请求。
- **SC-003**: 文档包含 CrewAI / AutoGen 的最小接入片段。
- **SC-004**: 核心模块覆盖率 ≥90%；全量测试断网通过。
- **SC-005**: 既有 001–006 全部测试无回归。

---

## Out of Scope

- **完整框架适配器**（驱动整图/整 agent loop）：见 research R-01/R-05，副作用拦截点在工具
  函数，完整适配器是过度设计（宪法第 VII 条）。
- **OpenAI Agents SDK / CrewAI / AutoGen 的 handoff、guardrail、memory 等框架运行时语义**：
  本工具只关心工具函数的副作用，不介入框架编排。
- **真实 LLM API 调用**：宪法第 III 条禁止；所有示例用 scripted model / mock。
- **其他框架（LlamaIndex、LangChain Agent 等）**：独立特性，按需扩展。

---

## Assumptions

- 三个框架的工具函数本质是普通 Python callable，可用 `guard.effect()` 装饰（research R-01）。
- OpenAI Agents SDK 的 `ScriptedModel` 官方设施可离线跑工具管线（research R-02）。
- 证据来源：框架官方文档与社区指南（research R-02~R-04），属「能力缺口」类证据（宪法第 I 条）。
