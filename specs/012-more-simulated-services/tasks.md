---
description: "Task list for 012 more simulated services"
---

# Tasks: 更多模拟服务模板（订单/邮件/库存）

**Input**: Design documents from `/specs/012-more-simulated-services/`

**Tests**: 测试先行是强制要求（宪法第 IV 条）。

---

## Phase 0: 前置与基线（Setup）

- [x] T001 `pyproject.toml` 版本 bump 到 0.12.0
- [x] T002 运行基线：`pytest -q`、`ruff check .`、`mypy src/agentreplayguard`、`coverage
  --fail-under=90`，记录全绿

---

## Phase 1: 三个模拟服务（Priority: P1）🎯

- [x] T003 [P] 编写 `tests/unit/test_simulated_services.py`：订单/邮件/库存三个服务的幂等
  去重、重复检测、幂等键冲突、count/查询接口（复用退款服务语义）
- [x] T004 [P] 实现 `services/order.py`：`SimulatedOrderService` + `Order`
- [x] T005 [P] 实现 `services/email.py`：`SimulatedEmailService` + `Email`
- [x] T006 [P] 实现 `services/inventory.py`：`SimulatedInventoryService` + `InventoryOp`
- [x] T007 抽取共享 `IdempotencyConflict`（若需）到 `services/_common.py`，退款服务改为导入

---

## Phase 2: 集成示例与文档（Integration & Docs）

- [x] T008 [P] 编写 `examples/more_services/test_order_lost_ack.py`：guard 装饰 + lost-ack
  重复检测示例（至少订单服务）
- [x] T009 [P] 更新 `docs/quickstart.md`：更多模拟服务模板用法
- [x] T010 [P] 更新 `README.md`：能力清单 + 路线图勾选 012

---

## Phase 3: 全量验证（Verification）

- [x] T011 全流程：`pytest tests examples`、`ruff check .`、`mypy src/agentreplayguard`、
  `coverage report --fail-under=90`，核对 001–011 无回归

---

## Notes

- **不碰核心模块**：只在 `services/` 与 `examples/` 下新增（宪法 VI）。
- **范式复用**：三个服务复用退款服务的「内存账本 + 幂等键」模式（research R-01）。
- **克制**：不做完整 LangGraph 图（YAGNI），用户仿照退款示例接入。
