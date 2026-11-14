# Feature Specification: 流式响应体丢失语义（httpx 传输层）

**Feature Branch**: `009-stream-body-loss`

**Created**: 2026-11-13

**Status**: Implemented

**Input**: User description: "流式响应体丢失语义（003 的流式扩展）"

## 背景与问题

003 的 httpx 传输层适配器以「响应头到达」为提交边界：`FaultyTransport.handle_request`
返回 `Response` 即记 `committed`。但「响应头到达后、响应体（body）流式读取时丢失/中断」
这一故障——即服务端已提交副作用、客户端流式读响应体时失败——目前既无法注入，也无法追踪
（body 读取发生在 guard 之外，见 research R-01/R-02）。

这是 lost-ack 的一个更细粒度变体：与 `TIMEOUT_AFTER_COMMIT`（响应头都丢了）不同，它表现为
「响应头正常返回、但 body 读取时中断」。业务代码在流式读取时捕获异常并重试，会导致重复
副作用。

本特性新增 `FaultKind.STREAM_BODY_LOSS`，让 httpx 传输层能注入「响应头正常、body 读取时抛
`ReadError`」的故障，复用 `NoDuplicateEffects` 检测由此产生的重复副作用。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 注入流式响应体丢失故障（同步）(Priority: P1)

用户用 `httpx.Client(stream=True)` 流式读取退款响应，注入 `STREAM_BODY_LOSS` 后，响应头正常
返回、读 body 时抛 `ReadError`，effect 记为 committed。

**Why this priority**: 这是本特性的核心——补齐「响应体丢失」这个 lost-ack 变体的故障注入。

**Independent Test**: 注入 `STREAM_BODY_LOSS`，`FaultyTransport` 返回响应头正常的 Response，
`response.read()` 抛 `httpx.ReadError`，effect 记录 1 条 committed（fault=stream_body_loss）。

**Acceptance Scenarios**:

1. **Given** 注入 `STREAM_BODY_LOSS`，**When** 用 `FaultyTransport` 流式请求并读 body，
   **Then** 响应头正常（status 200），`read()` 抛 `httpx.ReadError`，effect 记录 committed 且
   `fault=STREAM_BODY_LOSS`。
2. **Given** 未注入该故障，**When** 流式读 body，**Then** body 正常返回，effect committed 且
   `fault=None`。

---

### User Story 2 - 异步流式响应体丢失 (Priority: P1)

用户用 `httpx.AsyncClient` 异步流式读取，注入 `STREAM_BODY_LOSS` 后同样抛 `ReadError`。

**Why this priority**: 与同步对称，异步是 httpx 的另一半使用面。

**Independent Test**: `AsyncFaultyTransport` + `STREAM_BODY_LOSS`，`aread()` 抛 `ReadError`，
effect committed 且 fault 正确。

**Acceptance Scenarios**:

1. **Given** 注入 `STREAM_BODY_LOSS`，**When** 用 `AsyncFaultyTransport` 异步流式读 body，
   **Then** `aread()` 抛 `httpx.ReadError`，effect committed 且 `fault=STREAM_BODY_LOSS`。

---

### User Story 3 - 流式丢失后重试的重复副作用检测 (Priority: P1)

用户流式读取失败后重试，希望 `NoDuplicateEffects` 检测到重复副作用。

**Why this priority**: 这是故障注入的最终价值——把流式丢失导致的重复变成可断言。

**Independent Test**: 注入 `STREAM_BODY_LOSS`，业务代码捕获 `ReadError` 后重试同一请求，
`NoDuplicateEffects` 检测到 2 条 committed、`ok=False`。

**Acceptance Scenarios**:

1. **Given** 注入 `STREAM_BODY_LOSS`（attempt=1）+ 业务侧重试，**When** 两次请求同一 key
   （无幂等键），**Then** `committed_count=2`、`NoDuplicateEffects` 报违规。
2. **Given** 相同场景带相同幂等键，**When** 重试，**Then** `committed_count=1`、`ok=True`。

---

### Edge Cases

- **非流式读取**：`client.send()` 默认读完整 body，`STREAM_BODY_LOSS` 的故障会表现为
  `send()` 内部抛 `ReadError`（因为 send 内部 `response.read()`），语义仍成立（effect committed）。
- **body 空响应**：body 为空时无「丢失」可注入，应正常返回（或按故障规则，空 body 时故障
  无意义，需明确）。
- **未分类请求**：`classify` 返回 None 的请求透传，不注入流式故障。
- **提交前故障优先级**：`STREAM_BODY_LOSS` 是提交后故障，不影响 `is_before_commit` 判断。

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `FaultKind` MUST 新增 `STREAM_BODY_LOSS = "stream_body_loss"`（提交后故障，
  不在 `_BEFORE_COMMIT` 集合）。
- **FR-002**: `FaultyTransport`（同步）MUST 在注入 `STREAM_BODY_LOSS` 时，返回一个响应头
  正常、body 读取时抛 `httpx.ReadError` 的 Response；effect 记 committed 且 `fault=
  STREAM_BODY_LOSS`。
- **FR-003**: `AsyncFaultyTransport`（异步）MUST 对称实现（body 读取时抛 `ReadError`）。
- **FR-004**: `_map_injected_fault` 与 guard 的故障→异常映射 MUST 覆盖 `STREAM_BODY_LOSS`
  （映射为 `ReadError`）。
- **FR-005**: 复用 `NoDuplicateEffects` 检测流式丢失后重试的重复，不新增不变量。
- **FR-006**: 未分类请求 MUST 透传，不注入流式故障。
- **FR-007**: 既有五类故障（TIMEOUT_BEFORE/AFTER、CONNECTION_RESET、SERVER_ERROR、
  PARTIAL_SUCCESS）行为不变（回归）。
- **FR-008**: 核心包导入不因缺 httpx 失败；`faults.py` 的 `FaultKind` 枚举与
  `fault_exception`/`is_before_commit` 同步更新。

### Key Entities

- **FaultKind.STREAM_BODY_LOSS**：新故障枚举值。
- **无新增数据结构**：复用 `EffectRecord`、`HttpEffect`、不变量。

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 注入 `STREAM_BODY_LOSS` 后，流式读 body 抛 `ReadError`，effect committed 且
  `fault=STREAM_BODY_LOSS`（同步 + 异步）。
- **SC-002**: 流式丢失 + 重试（无幂等键）`committed_count=2`、`ok=False`；幂等键折叠为 1。
- **SC-003**: 未分类请求透传，不注入流式故障。
- **SC-004**: 核心模块覆盖率 ≥90%；既有 001–008 测试无回归。

---

## Out of Scope

- **requests 流式 body 丢失**：见 research R-04，requests 适配器（006）使用面窄、机制复杂，
  本轮不做。
- **上传下载断点续传**：003 已排除，维持排除。
- **其他 HTTP 客户端**（aiohttp/urllib3）：独立特性。

---

## Assumptions

- httpx 受支持版本 0.27–1.0，`SyncByteStream`/`AsyncByteStream` 接口稳定（实测 0.28.1）。
- 流式 body 丢失是「提交后」故障（副作用已提交），映射为 `ReadError`。
- 证据来源：003 的 Out of Scope（第 122/182 行）+ 实测注入机制（research R-02）。
