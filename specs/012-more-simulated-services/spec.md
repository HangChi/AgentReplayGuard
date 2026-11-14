# Feature Specification: 更多模拟服务模板（订单/邮件/库存）

**Feature Branch**: `012-more-simulated-services`

**Created**: 2026-11-14

**Status**: Implemented

**Input**: User description: "B 类扩展，做更多模拟服务模板"

## 背景与问题

当前只有 `SimulatedRefundService`（退款）一个模拟服务参考实现。产品定位文档第 100-113 行
P2 规划了「更多内置模拟服务模板（邮件、订单、库存）」，帮助用户仿照接入自己的外部服务
模拟（支付、退款、写入、通知等副作用）。

本特性新增订单、邮件、库存三类模拟服务，复用退款服务的「内存账本 + 幂等键」范式，每个
配最小示例，证明范式可复制。不涉及核心模块改动（宪法第 VI 条）。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 订单模拟服务 (Priority: P1)

用户需要一个下单模拟服务，验证重复下单被检测。

**Why this priority**: 订单是「资金/写入」类副作用的典型代表，覆盖产品定位的核心场景。

**Independent Test**: 同一 order_id 提交两次 → 账本两条记录；`NoDuplicateEffects` 报违规。

**Acceptance Scenarios**:

1. **Given** 订单服务，**When** 同 order_id 下单两次，**Then** 账本两条记录，`NoDuplicateEffects`
   检测到重复。
2. **Given** 同幂等键下单两次（同参数），**Then** 账本一条记录（幂等去重）。

---

### User Story 2 - 邮件模拟服务 (Priority: P1)

用户需要一个通知/邮件发送模拟服务，验证重复发送被检测。

**Why this priority**: 通知类副作用是产品定位明确列举的类型。

**Independent Test**: 同一 notification_id 发送两次 → 账本两条；`NoDuplicateEffects` 报违规。

**Acceptance Scenarios**:

1. **Given** 邮件服务，**When** 同 notification_id 发送两次，**Then** 账本两条，检测到重复。
2. **Given** 同幂等键发送两次（同内容），**Then** 账本一条（幂等去重）。

---

### User Story 3 - 库存模拟服务 (Priority: P1)

用户需要一个库存扣减模拟服务，验证重复扣减被检测。

**Why this priority**: 库存是「状态变更」类副作用的代表，覆盖扣减/回补的幂等语义。

**Independent Test**: 同一操作幂等键扣减两次 → 账本一条（幂等）；不同幂等键同 SKU 扣减
两次 → 账本两条，检测到重复。

**Acceptance Scenarios**:

1. **Given** 库存服务，**When** 同幂等键扣减同 SKU 两次，**Then** 账本一条（幂等去重）。
2. **Given** 不同幂等键扣减同 SKU 两次，**Then** 账本两条，`NoDuplicateEffects` 检测到重复。

---

### Edge Cases

- **幂等键冲突**：同键不同参数（订单金额不同、邮件内容不同、库存数量不同）→ 抛
  `IdempotencyConflict`（复用退款服务的异常类型）。
- **空业务键 / 空幂等键**：与退款服务一致，业务键非空是重复检测前提。
- **计数与查询接口**：每个服务提供 `count()` 与按业务键/幂等键查询，语义与退款服务一致。

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 新增 `services/order.py`：`SimulatedOrderService`（内存账本 + 幂等键），
  `dataclass` 记录订单（order_id、amount_cents、幂等键、提交序号、账本序号）。
- **FR-002**: 新增 `services/email.py`：`SimulatedEmailService`（内存账本 + 幂等键），
  `dataclass` 记录邮件（notification_id、subject/body、幂等键、序号）。
- **FR-003**: 新增 `services/inventory.py`：`SimulatedInventoryService`（内存账本 + 幂等键），
  `dataclass` 记录库存操作（sku、operation、quantity、幂等键、序号）。
- **FR-004**: 三个服务 MUST 复用退款服务的范式：frozen dataclass 记录、内存账本、按业务键/
  幂等键索引、幂等键冲突抛 `IdempotencyConflict`、`count()` 与查询接口。
- **FR-005**: 每个服务 MUST 配一个独立单元测试（幂等去重、重复检测、幂等键冲突）。
- **FR-006**: 至少一个服务 MUST 配一个「guard 装饰 + lost-ack 重复检测」示例，证明与
  `Scenario`/`NoDuplicateEffects` 集成。
- **FR-007**: 不改动核心模块（guard/effect/fault/invariant/scenario）语义（宪法 VI）。
- **FR-008**: 仅标准库，不新增第三方依赖。

### Key Entities

- **SimulatedOrderService / Order**：下单副作用。
- **SimulatedEmailService / Email**：通知副作用。
- **SimulatedInventoryService / InventoryOp**：库存操作副作用。
- **复用** `IdempotencyConflict`（从 `services/refund.py` 导入或抽取共享）。

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 三个服务的幂等去重、重复检测、幂等键冲突语义与退款服务一致。
- **SC-002**: 同业务键提交两次 → `NoDuplicateEffects` 报违规；同幂等键（同参数）→ 折叠为 1。
- **SC-003**: 核心模块覆盖率 ≥90%；既有 001–011 测试无回归。
- **SC-004**: 全部测试断网通过（服务纯内存，无外部调用）。

---

## Out of Scope

- **完整的 LangGraph 图示例**：三个服务只配最小示例（服务 + 单测），不做完整 graph/conftest
  （用户仿照退款示例接入，YAGNI）。
- **遥测、真实服务、Web UI、流量录制回放**：违反宪法第 III 条，明确不做。
- **自动幂等修复 / 自动生成幂等键**：001 已排除，维持排除。

---

## Assumptions

- 三个服务的幂等语义与退款服务一致（同键同参数 → 幂等；同键不同参数 → 冲突）。
- 服务是框架无关的纯标准库实现，LangGraph 图由用户在示例层接入。
- 证据来源：产品定位 P2 规划 + 退款服务的既定范式（research R-01）。
