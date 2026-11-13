---
description: "Task list for 004 concurrent/parallel graph race detection"
---

# Tasks: 并发与并行图的副作用竞态与线性一致性检测

**Input**: Design documents from `/specs/004-concurrent-parallel-graph/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: 测试先行是强制要求（宪法第 IV 条）。每个模块先写失败测试，再实现。

**Organization**: 按用户故事分组，每个故事可独立实现与验证。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件，无依赖）
- **[Story]**: 所属用户故事（US1–US3）

## Path Conventions

- 单包 `src/` 布局；测试分 `tests/unit`、`tests/contract`、`tests/integration`。
- 分支归属契约见 `specs/004-concurrent-parallel-graph/contracts/branch-attribution.md`。

---

## Phase 0: 前置与基线（Setup）

**Purpose**: 锁版本、建回归基线，确保后续改造不破坏既有行为。

- [ ] T001 将 `pyproject.toml` 版本提升到 `0.4.0`（SemVer minor：新增并行检测能力）
- [ ] T002 运行 `uv run pytest -q`、`uv run ruff check .`、`uv run mypy src/agentreplayguard`、
  `uv run coverage run -m pytest -q && uv run coverage report --fail-under=90`，记录基线全绿
- [ ] T003 确认当前分支为 `004-concurrent-parallel-graph`，且设计文档齐全

---

## Phase 1: 数据模型（Foundational）

**Purpose**: `branch_id` 字段与可注入 branch resolver，是所有故事的基础。

- [ ] T004 [P] 编写 `tests/unit/test_effect_branch.py`：`EffectRecord` 含 `branch_id` 字段，
  默认为 `None`，赋值后确定性；序列化/相等性不因字段破坏
- [ ] T005 [P] 编写 `tests/unit/test_guard_branch.py`：`EffectGuard` 接受可注入
  `branch_resolver`，默认 `None`；注入后 `_begin_attempt` 写入 `branch_id`
- [ ] T006 在 `src/agentreplayguard/effects.py` 的 `EffectRecord` 增加 `branch_id: str | None`
  字段（默认 `None`），并同步 `EffectGuard._record_outcome` 写入
- [ ] T007 在 `src/agentreplayguard/guard.py` 的 `EffectGuard` 增加可注入 `branch_resolver`
  参数（默认返回 `None`），`_begin_attempt` 读取并透传到 `_Attempt`

---

## Phase 2: User Story 1 — 允许并行图运行并记录分支归属 (Priority: P1) 🎯

**Goal**: fan-out 图不再被拒绝，effect 记录能区分分支归属。

**Independent Test**: `a → (b, c) → END` 图在 `strict_graph=True` 下 `invoke` 成功，effect
记录 `branch_id` 分别归属 b、c。

### Tests for US1 ⚠️

- [ ] T008 [P] [US1] 编写 `tests/integration/test_parallel_graph.py`：fan-out 图
  `strict_graph=True` 下 `invoke` 成功；两分支 effect `branch_id` 分别为 b/c（节点名）；串行图
  `branch_id is None`；连跑 20 次检测结论与 branch_id 归属一致
- [ ] T009 [P] [US1] 编写 `tests/contract/test_branch_attribution.py`：`EffectRecord.branch_id`
  公开可见；`strict_graph` 语义（True 支持 fan-out、False 仅警告）符合 FR-008

### Implementation for US1

- [ ] T010 [US1] 改造 `src/agentreplayguard/adapters/langgraph.py`：`_find_fanout` 不再拒绝；
  构造时注入读 `get_config()['metadata']['langgraph_node']` 的 branch resolver 到 Scenario
- [ ] T011 [US1] `_validate_graph` 调整：`strict_graph=True` 时 fan-out 合法；保留
  `strict_graph=False` 的警告路径

---

## Phase 3: User Story 2 — 检测并行分支重复副作用 (Priority: P1) 🎯

**Goal**: 并行分支提交同一业务键时，`NoDuplicateEffects` 报 `duplicate_effects` 且能定位分支。

**Independent Test**: fan-out 图两分支提交同一 key（无幂等键），`ok=False`，`actual=2`，
effect_ids 两条分支归属不同。

### Tests for US2 ⚠️

- [ ] T012 [P] [US2] 扩展 `tests/integration/test_parallel_graph.py`：两分支同 key（无幂等键）
  报 `duplicate_effects` 且 branch_id 不同；同 key + 相同幂等键 `committed_count=1`；同 key +
  相同幂等键 + 不同参数报 `parameter_mismatch`
- [ ] T013 [P] [US2] 编写 `tests/unit/test_invariants_parallel.py`：`NoDuplicateEffects` 在带
  `branch_id` 的记录上仍正确去重，报告能区分分支

### Implementation for US2

- [ ] T014 [US2] 确认 `NoDuplicateEffects` 无需改动即可检测并行重复（去重口径与 branch_id
  无关）；仅在报告/违规信息中补充 branch_id 定位（如 `report.py` 的 effect 行输出）

---

## Phase 4: User Story 3 — 检测异步交错下的并发提交 (Priority: P3)

**Goal**: 异步交错/手动并发的同 key 提交，通过区间重叠判定识别为「并发」。

**Independent Test**: `asyncio.gather` 并发两个 `acall` 同一 key（无幂等键），
`ConcurrentCommitDetected` 报违规。

### Tests for US3 ⚠️

- [ ] T015 [P] [US3] 编写 `tests/unit/test_concurrent_commit.py`：区间重叠判定正确（相交/相离/
  相邻边界）；`ConcurrentCommitDetected` 对 gather 并发同 key 报违规、顺序执行不报、不同 key
  不报
- [ ] T016 [P] [US3] 扩展 `tests/contract/test_branch_attribution.py`：`ConcurrentCommitDetected`
  公开签名与既有不变量风格一致

### Implementation for US3

- [ ] T017 [US3] 在 `src/agentreplayguard/invariants.py` 新增 `ConcurrentCommitDetected`，
  复用 `started_tick`/`ended_tick` 区间重叠判定
- [ ] T018 [US3] 新增区间重叠判定工具（可放 invariants 内部或独立纯函数），含边界语义注释

---

## Phase 5: 文档与示例（Docs & Examples）

- [ ] T019 [P] 新增 `examples/refund/graph_parallel.py` 与
  `examples/refund/test_refund_parallel.py`：并行重复退款示例（含幂等键通过 / 无幂等键失败）
- [ ] T020 [P] 更新 `docs/quickstart.md`：新增并行图用法、`branch_id` 说明、`InvalidUpdateError`
  注意事项
- [ ] T021 [P] 更新 `README.md`：能力清单加入并行检测，路线图勾选 004

---

## Phase 6: 全量验证（Verification）

- [ ] T022 运行 `specs/004-concurrent-parallel-graph/quickstart.md` 全流程：`pytest tests
  examples/refund`、`ruff check .`、`mypy src/agentreplayguard`、`coverage report
  --fail-under=90`
- [ ] T023 核对 001/002/003 无回归（串行图行为不变），确认公开 API 无破坏性变更
- [ ] T024 确定性回归：连跑 20 次 fan-out 场景，检测结论与 branch_id 归属 20/20 一致
  （effect 追加 sequence 顺序可抖动，不断言）

---

## Notes（贯穿全清单的硬约束）

- **确定性**：branch_id 归属、检测结论（重复/并发/参数不一致）必须只依赖「图结构」，与
  调度无关；effect 追加 `sequence`/tick 顺序在真并发下可抖动（宪法第 II 条「并发调度标注」）。
- **框架隔离**：`effects.py`/`guard.py`/`invariants.py`/`report.py` 不得 import langgraph；
  分支归属通过可注入 resolver 隔离，框架依赖只在 `adapters/langgraph.py`。
- **无新依赖**：仅用标准库，不新增第三方依赖。
- **真线程并发已支持**：同步 fan-out 本身就是线程池并发（实测），本特性支持它而非排除；
  但**多进程**并发仍 Out of Scope。
