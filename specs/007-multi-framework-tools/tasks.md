---
description: "Task list for 007 multi-framework tool guard"
---

# Tasks: 多框架工具副作用记账

**Input**: Design documents from `/specs/007-multi-framework-tools/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: 测试先行是强制要求（宪法第 IV 条）。

## Format: `[ID] [P?] [Story] Description`

---

## Phase 0: 前置与基线（Setup）

- [ ] T001 `pyproject.toml` 版本 bump 到 0.7.0
- [ ] T002 运行基线：`pytest -q`、`ruff check .`、`mypy src/agentreplayguard`、`coverage
  --fail-under=90`，记录全绿

---

## Phase 1: User Story 1 — 框架无关工具函数级测试 (Priority: P1) 🎯

**Goal**: 证明 guard.effect 装饰 callable 即可记账（同步+异步+故障+重复）。

- [ ] T003 [P] [US1] 编写 `examples/multi_framework/test_tool_guard.py`：同步/异步工具函数
  记账、lost-ack 重复检测、幂等键折叠、注入故障
- [ ] T004 [US1] 确认复用 guard.effect 无需新增产品代码

---

## Phase 2: User Story 2 — OpenAI Agents SDK scripted 示例 (Priority: P1) 🎯

**Goal**: scripted 工具流程离线跑，effect 正确记账。

- [ ] T005 [P] [US2] 编写 `examples/multi_framework/test_openai_agents_sdk.py`（
  `pytest.importorskip("agents")` 守卫）：scripted function_call 流程 + guard 记账 + 故障注入
- [ ] T006 [US2] 实测装饰器叠加顺序（@tool 与 @guard.effect），在示例中锁定

---

## Phase 3: User Story 3 — CrewAI / AutoGen 接入文档 (Priority: P2)

- [ ] T007 [P] [US3] 编写 `examples/multi_framework/README.md`：CrewAI / AutoGen 最小接入
  片段（工具函数直接调用 + guard 装饰）

---

## Phase 3b: User Story 4 — 真实 LLM 集成演示 (Priority: P3，不进 CI)

- [ ] T007b [US4] 编写 `examples/multi_framework/demo_real_llm.py`：从环境变量读
  `OPENAI_BASE_URL`/`OPENAI_API_KEY`（未提供则跳过），真实 agent 调用带 guard 的退款工具，
  注入 lost-ack 后检测重复副作用；不硬编码密钥、不进 pytest 测试路径

---

## Phase 4: 文档（Docs）

- [ ] T008 [P] 更新 `docs/quickstart.md`：多框架工具函数接入章节
- [ ] T009 [P] 更新 `README.md`：能力清单 + 路线图勾选 007

---

## Phase 5: 全量验证（Verification）

- [ ] T010 全流程：`pytest tests examples`、`ruff check .`、`mypy src/agentreplayguard`、
  `coverage report --fail-under=90`
- [ ] T011 核对 001–006 无回归

---

## Notes

- **无新公开 API**：复用 `guard.effect`；核心 `src/` 无改动。
- **可选依赖隔离**：`openai-agents` 仅示例用，`pytest.importorskip` 守卫，不进 dev extra。
- **全离线**：scripted model 无真实 LLM（宪法第 III 条）。
