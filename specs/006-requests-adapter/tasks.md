---
description: "Task list for 006 requests adapter"
---

# Tasks: requests 客户端的副作用记账与故障注入适配器

**Input**: Design documents from `/specs/006-requests-adapter/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: 测试先行是强制要求（宪法第 IV 条）。

## Format: `[ID] [P?] [Story] Description`

---

## Phase 0: 前置与基线（Setup）

- [x] T001 `pyproject.toml` 版本 bump 到 0.6.0，新增可选 extra `requests`，`uv lock` + `uv sync`
- [x] T002 运行基线：`pytest -q`、`ruff check .`、`mypy src/agentreplayguard`、`coverage
  --fail-under=90`，记录全绿

---

## Phase 1: 抽取共享 HttpEffect（Foundational）

**Purpose**: 让 requests 复用 HttpEffect 而不 import httpx。

- [x] T003 [P] 编写 `tests/unit/test_http_common.py`：`HttpEffect` 字段与校验逻辑不变；从
  `_http_common` 导入与从 `adapters.httpx` 导入等价
- [x] T004 新建 `src/agentreplayguard/adapters/_http_common.py`，抽取 `HttpEffect` 与
  `_classify_or_raise`（仅标准库）；`adapters/httpx.py` 改为从 `_http_common` 导入并 re-export

---

## Phase 2: User Story 1 & 2 — requests 记账与故障映射 (Priority: P1) 🎯

**Goal**: `RequestsAdapter` 记账 + 五类故障映射为 requests 异常。

- [x] T005 [P] [US1/US2] 编写 `tests/unit/test_requests_adapter.py`：正常分类记账 committed；
  未分类透传；分类异常包装；五类故障映射（RA-04~RA-08）；base 自身异常原样传播；close 委托
- [x] T006 [US1/US2] 实现 `src/agentreplayguard/adapters/requests.py`：`RequestsAdapter` 类，
  可选依赖 import 守卫，故障映射表，`send`/`close`

---

## Phase 3: User Story 3 — lost-ack 重复检测 (Priority: P1) 🎯

**Goal**: lost-ack + 重试的重复副作用被 NoDuplicateEffects 检测。

- [x] T007 [P] [US3] 编写 `tests/integration/test_requests_lost_ack.py`：lost-ack + 重试
  `committed_count=2`、`ok=False`；幂等键折叠为 1；与 httpx 适配器结论一致
- [x] T008 [US3] 确认复用 NoDuplicateEffects 无需新增逻辑

---

## Phase 4: 文档与示例（Docs & Examples）

- [x] T009 [P] 新增 `examples/refund/test_refund_requests.py`：requests 退款 lost-ack 示例
- [x] T010 [P] 更新 `docs/quickstart.md`：requests 用法
- [x] T011 [P] 更新 `README.md`：能力清单 + 路线图勾选 006

---

## Phase 5: 全量验证（Verification）

- [x] T012 全流程：`pytest tests examples/refund`、`ruff check .`、`mypy src/agentreplayguard`、
  `coverage report --fail-under=90`
- [x] T013 核对 001–005 无回归，确认公开 API 无破坏性变更（HttpEffect re-export 兼容）

---

## Notes

- **共享 HttpEffect**：抽取到 `_http_common.py`（仅标准库），httpx 与 requests 共用；
  `adapters.httpx.HttpEffect` 保持 re-export 向后兼容。
- **框架/库隔离**：核心模块不 import requests/httpx；适配器模块独立 import。
- **无新核心依赖**：requests 是可选 extra，核心包运行时仍仅标准库。
