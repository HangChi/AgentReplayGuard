# Feature Specification: requests 客户端的副作用记账与故障注入适配器

**Feature Branch**: `006-requests-adapter`

**Created**: 2026-11-13

**Status**: Implemented

**Input**: User description: "A 类剩余扩展逐个完成，从其他 HTTP 客户端适配器（requests）开始"

## 背景与问题

003 已为 `httpx` 提供传输层适配器（`FaultyTransport`/`AsyncFaultyTransport`），让 HTTP 请求
零改动接入 EffectGuard 的记账与故障注入。但 Python 生态里 `requests` 是最广泛使用的 HTTP
客户端，大量 Agent 工具的副作用经由 `requests` 发出。当前工具无法覆盖这些调用。

本特性为 `requests` 提供对称的适配器：通过官方 `BaseAdapter` 接缝（`Session.mount`），让
业务代码零改动地把请求接入副作用记账、确定性故障注入与重复检测，语义与 003 的 httpx
适配器一致。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - requests 请求的副作用记账 (Priority: P1)

用户用 `requests.Session` 发起的写操作（退款、下单等），希望通过挂载适配器自动记账。

**Why this priority**: 记账是所有检测的前提，也是适配器的基础能力。

**Independent Test**: 挂载 `RequestsAdapter` 后，`session.post(...)` 一个被分类的请求，
effect 记录一条 committed，业务键/参数哈希正确。

**Acceptance Scenarios**:

1. **Given** 挂载适配器且分类函数对 POST 返回 `HttpEffect`，**When** `session.post` 执行，
   **Then** effect 记录 1 条 committed，业务键与参数哈希与分类结果一致。
2. **Given** 分类函数返回 `None`（如 GET），**When** 执行，**Then** 请求透传底层 adapter，
   不产生 effect 记录、不消耗故障计划。
3. **Given** 分类函数抛异常，**When** 执行，**Then** 包装为 `ScenarioConfigError`，不调用
   底层 adapter。

---

### User Story 2 - requests 故障注入与异常映射 (Priority: P1)

用户希望在 requests 调用上注入 lost-ack 等故障，且故障转换为 requests 标准异常，使业务侧
既有重试逻辑原样生效。

**Why this priority**: 故障注入是本工具的核心能力，异常映射是 requests 生态正确性的关键。

**Independent Test**: 注入 `TIMEOUT_AFTER_COMMIT` 后，`session.post` 抛 `requests.exceptions.
ReadTimeout`，且 effect 记录 committed（提交后故障）。

**Acceptance Scenarios**:

1. **Given** 注入 `TIMEOUT_BEFORE_COMMIT`，**When** 执行，**Then** 抛 `ConnectTimeout`，
   effect `not_committed`，底层 adapter 未被调用。
2. **Given** 注入 `TIMEOUT_AFTER_COMMIT`，**When** 执行，**Then** 抛 `ReadTimeout`，effect
   `committed`。
3. **Given** 注入 `CONNECTION_RESET`，**When** 执行，**Then** 抛 `ConnectionError`。
4. **Given** 注入 `SERVER_ERROR`，**When** 执行，**Then** 抛 `HTTPError`（响应 500）。
5. **Given** 注入 `PARTIAL_SUCCESS`，**When** 执行，**Then** 抛 `ChunkedEncodingError`。
6. **Given** 底层 adapter 自身抛异常（非注入故障），**When** 执行，**Then** effect 记录
   `not_committed`，异常原样传播。

---

### User Story 3 - lost-ack 重复副作用检测 (Priority: P1)

用户用 requests 发起的退款在 lost-ack + 重试下产生重复，希望 `NoDuplicateEffects` 检测到。

**Why this priority**: 这是适配器的最终价值——把 requests 副作用的 exactly-once 变成可断言。

**Independent Test**: lost-ack + retry 场景下，`NoDuplicateEffects` 检测到 2 条 committed、
`ok=False`；有幂等键时折叠为 1。

**Acceptance Scenarios**:

1. **Given** lost-ack 故障 + 业务侧重试，**When** 执行两次 `session.post`（同 key 无幂等键），
   **Then** `committed_count=2`、`NoDuplicateEffects` 报违规。
2. **Given** 相同场景但带相同幂等键，**When** 执行，**Then** `committed_count=1`、`ok=True`。

---

### Edge Cases

- **JSON body 解析失败**：分类函数读 `request.body` 时 JSON 非法，应包装为
  `ScenarioConfigError`（分类失败），而非透传。
- **非 JSON 请求体**：表单/二进制 body，分类函数应自行处理或返回 None。
- **`close()` 委托**：适配器 `close()` 应委托底层 adapter（对齐 003 的 `close` 委托）。
- **空业务键 / 非可序列化参数**：沿用 `HttpEffect` 的校验，快速失败。

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 新增 `agentreplayguard.adapters.requests` 模块，`requests` 作为可选依赖，未安装
  时导入抛可操作的 `ImportError`。
- **FR-002**: 新增 `RequestsAdapter(requests.adapters.BaseAdapter)`，构造接受 `base`、
  `scenario`、`classify`，`send()` 对已分类请求调用 `scenario.guard().call`，未分类透传。
- **FR-003**: 分类回调签名 `Callable[[requests.PreparedRequest], HttpEffect | None]`，复用
  `HttpEffect` 数据类（从 003 的 `adapters/httpx.py` 导入或抽取共享）。
- **FR-004**: 注入故障转换为 `requests.exceptions` 标准异常（映射见 research R-02），非注入
  异常原样传播。
- **FR-005**: `close()` 委托底层 adapter；`send()` 对提交前故障不调用底层 adapter。
- **FR-006**: 复用 `EffectGuard.call` 完成 attempt 记账、参数哈希与故障注入，不新增第二套逻辑。
- **FR-007**: 核心包导入不因缺 requests 失败（适配器模块独立导入）。
- **FR-008**: 现有公开 API 与 003 httpx 适配器行为不变。

### Key Entities

- **RequestsAdapter**：`BaseAdapter` 子类，同步 HTTP 请求的副作用记账与故障注入入口。
- **无新增数据结构**：复用 `HttpEffect`、`EffectRecord`、`Scenario`。

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 挂载适配器后 POST 被分类请求记录 1 条 committed，业务键正确。
- **SC-002**: 五类故障均映射为对应 requests 异常（research R-02 表），提交前不调用底层 adapter。
- **SC-003**: lost-ack + 重试检测到 `committed_count=2`、`ok=False`；幂等键场景折叠为 1。
- **SC-004**: 核心模块覆盖率 ≥90%；全量测试断网通过（requests 用内存 mock，无真实 socket）。
- **SC-005**: 既有 001–005 全部测试无回归。

---

## Out of Scope

- **urllib3 / aiohttp 适配器**：见 research R-03，独立特性，本轮不做。
- **requests 异步**（无原生异步，`requests` 本身同步）：不涉及。
- **流式响应体丢失 / 断点续传**：属 HTTP 流式语义，独立特性（005 已做 LangGraph 流式，HTTP
  流式响应体不在本阶段）。
- **真实外部服务调用**：宪法第 III 条禁止。
- **自动重试策略推导 / 鉴权 / 签名**：沿用 003 的 Out of Scope。

---

## Assumptions

- requests 受支持版本 2.x（实测 2.34.2），`BaseAdapter`/`PreparedRequest` 接口稳定。
- 分类函数仅依据请求本身（method/url/body/headers）确定副作用语义；无法确定返回 None 透传。
- requests 作为可选 extra 安装；核心包与现有示例不引入第三方运行时依赖。
- 所有测试用内存 mock adapter（无需真实 socket），不依赖真实网络/时钟/延迟。
- 证据来源：requests 生态空白（research R-05）+ 003 已有 httpx 模式的自然延伸。
