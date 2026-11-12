---
description: "Task list for AgentReplayGuard MVP implementation"
---

# Tasks: AgentReplayGuard MVP — LangGraph 副作用安全测试

**Input**: Design documents from `/specs/001-effect-safety-testing/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: 测试先行是强制要求（宪法原则 IV）。每个模块先写失败测试，再实现。

**Organization**: 按用户故事分组，每个故事可独立实现与验证。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件，无依赖）
- **[Story]**: 所属用户故事（US1–US6）

## Path Conventions

- 单包 `src/` 布局；测试分 `tests/unit`、`tests/contract`、`tests/integration`。
- 公开 API 契约见 `specs/001-effect-safety-testing/contracts/public-api.md`。

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 项目骨架（pyproject.toml 由 Phase 3 初始化创建，此处为可运行骨架的验证）。

- [X] T001 创建 `src/agentreplayguard/__init__.py`（空导出占位）与 `src/agentreplayguard/py.typed`
- [X] T002 [P] 创建 `tests/unit/`、`tests/contract/`、`tests/integration/` 目录与空 `conftest.py` 骨架
- [X] T003 [P] 验证 `pip install -e ".[dev,langgraph]"` 成功且 `import agentreplayguard` 可用
- [X] T004 [P] 验证 `ruff check .`、`mypy src/agentreplayguard` 在空包上无错误

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 所有用户故事依赖的核心数据模型与基础模块。完成后任何故事才可开始。

**⚠️ CRITICAL**: 本阶段未完成前，US1–US6 均不得开始。

- [X] T005 [P] 编写异常体系测试 `tests/unit/test_errors.py`：`EffectSafetyError` 继承 `AssertionError`、`ScenarioConfigError`、`ScenarioStateError`、`UnsupportedGraphError`、`ServiceError(status=...)`、`PartialSuccessError`、`IdempotencyConflict`
- [X] T006 实现 `src/agentreplayguard/errors.py`
- [X] T007 [P] 编写时钟测试 `tests/unit/test_clock.py`：单调递增、场景内序号 ID（`eff-000001`、`run-0001`）、确定性
- [X] T008 实现 `src/agentreplayguard/clock.py`（`LogicalClock` + 确定性 ID 生成）
- [X] T009 [P] 编写 effect 存储测试 `tests/unit/test_effects.py`：`EffectStatus` 枚举、`EffectRecord` 只读、`EffectStore` 查询、`committed_count` 去重口径（有幂等键相同哈希只计 1 次、无幂等键每条计 1 次）
- [X] T010 实现 `src/agentreplayguard/effects.py`（`EffectStatus`、`EffectRecord`、`EffectStore`、`EffectView`）
- [X] T011 [P] 编写故障模型测试 `tests/unit/test_faults.py`：规则顺序匹配、`times` 耗尽后继续、选择器校验、`probability` 与 seed 确定性
- [X] T012 实现 `src/agentreplayguard/faults.py`（`FaultKind`、`FaultRule`、`FaultPlan`）
- [X] T013 [P] 编写不变量测试 `tests/unit/test_invariants.py`：`NoDuplicateEffects`（去重口径、`parameter_mismatch`）、`MaxEffectCount`、`CustomInvariant`（predicate 抛异常视为违规）、`Violation` 排序
- [X] T014 实现 `src/agentreplayguard/invariants.py`（`Invariant` 协议、三个内置不变量、`Violation`）
- [X] T015 [P] 编写报告测试 `tests/unit/test_report.py`：`RunSegment`/`RunInputKind`/`GraphRun`、`ScenarioReport.ok`、`format()` 确定性（无 wall clock/绝对路径/内存地址）、`assert_clean()` 抛 `EffectSafetyError`
- [X] T016 实现 `src/agentreplayguard/report.py`（`RunInputKind`、`RunSegment`、`GraphRun`、`ScenarioReport`）

**Checkpoint**: 基础就绪，用户故事可开始。

---

## Phase 3: User Story 1 — 复现「提交后响应丢失」导致的重复退款 (Priority: P1) 🎯 MVP

**Goal**: 用户用 guard 包裹退款工具，注入 lost-ack 故障，检测同一业务键被提交两次并给出可定位报告。

**Independent Test**: 运行 `examples/refund/test_refund_lost_ack.py`，测试失败且报告含 2 条 committed `refund`。

### Tests for User Story 1 ⚠️

- [X] T017 [P] [US1] 契约测试 `tests/contract/test_public_api.py`：公开导入面、`Scenario` 构造与生命周期、`EffectGuard.effect` 签名保留
- [X] T018 [P] [US1] guard 单元测试 `tests/unit/test_guard.py`：参数绑定、key 提取、params 排除 key/idempotency_key、参数哈希、attempt 累计、提交前/后故障语义、异常透传
- [X] T019 [P] [US1] 场景测试 `tests/unit/test_scenario.py`：装配、RUNNING 状态、FINISHED 后禁止使用、`finish()` 幂等

### Implementation for User Story 1

- [X] T020 [P] [US1] 实现 `src/agentreplayguard/guard.py`（`EffectGuard`：`effect` 装饰器 + `call`，哈希、attempt、故障接线）
- [X] T021 [US1] 实现 `src/agentreplayguard/scenario.py`（`Scenario`：装配 store/clock/injector/invariants，生命周期）
- [X] T022 [P] [US1] 实现 `src/agentreplayguard/services/refund.py`（`SimulatedRefundService`、`Refund`、`IdempotencyConflict`）及测试 `tests/unit/test_refund.py`
- [X] T023 [US1] 实现 `src/agentreplayguard/__init__.py` 公开导出面（对齐 contracts/public-api.md）
- [X] T024 [US1] 编写退款示例 `examples/refund/tools.py`（退款/通知工具，用 guard 包裹）、`examples/refund/graph.py`（串行图，显式 `retry_on=(TimeoutError, ConnectionError, ServiceError)`、`initial_interval=0`、`jitter=False`）、`examples/refund/conftest.py`（`refund_scenario` fixture）
- [X] T025 [US1] 编写 `examples/refund/test_refund_lost_ack.py`：`test_duplicate_is_detected`（ok=False，2 条 committed）与 `test_lost_ack_demo_fails`（xfail，`assert_clean()` 抛 `EffectSafetyError`）

**Checkpoint**: US1 完整可独立验证。

---

## Phase 4: User Story 2 — 验证幂等键确实消除了重复副作用 (Priority: P1)

**Goal**: 加幂等键后重跑 lost-ack，账本仅 1 笔；错误实现（每次重试不同键）被再次检测。

**Independent Test**: 运行 `examples/refund/test_refund_idempotent.py`，通过且账本仅 1 笔。

### Tests for User Story 2 ⚠️

- [X] T026 [P] [US2] 幂等去重单元测试 `tests/unit/test_effects_idempotency.py`：相同键同参数不新增 committed 计数、相同键不同参数报 `parameter_mismatch`、无键重复计多次

### Implementation for User Story 2

- [X] T027 [US2] 编写 `examples/refund/test_refund_idempotent.py`：`test_idempotent_single_refund`（通过）、`test_varying_key_detected`（不同键被检测）
- [X] T028 [US2] 确认 `NoDuplicateEffects` 与 `committed_count` 去重口径在 US2 场景下正确（补充断言，无需新模块）

**Checkpoint**: US1 + US2 均可独立验证。

---

## Phase 5: User Story 3 — 验证 Checkpoint 恢复不会重复执行已完成的副作用 (Priority: P1)

**Goal**: 适配器驱动 resume，按 run/thread/checkpoint 归属 effect，区分「checkpoint 在 effect 后不重复」与「在 effect 前节点重跑则重复」。

**Independent Test**: 运行 `examples/refund/test_refund_resume.py` 与 `tests/integration/test_langgraph_resume.py`。

### Tests for User Story 3 ⚠️

- [X] T029 [P] [US3] 集成测试 `tests/integration/test_langgraph_resume.py`：effect 在 checkpoint 后 resume 不新增、effect 在 checkpoint 前 resume 新增并被检测、RunSegment 按 run_id 区分

### Implementation for User Story 3

- [X] T030 [US3] 实现 `src/agentreplayguard/adapters/langgraph.py`（`LangGraphAdapter`：`invoke`、`resume`、`state`、checkpoint 读取、RunSegment 上下文、`strict_graph` 检查）
- [X] T031 [P] [US3] 适配器单元测试 `tests/unit/test_adapter.py`（不依赖 langgraph，用假 graph stub 验证 checkpoint 读取与 RunSegment 生成、无 checkpointer 抛 `UnsupportedGraphError`）
- [X] T032 [US3] 编写 `examples/refund/test_refund_resume.py`：恢复后不新增 committed（effect 已完成场景）

**Checkpoint**: US1–US3 均可独立验证。

---

## Phase 6: User Story 4 — 验证 Interrupt 恢复后的重放安全性 (Priority: P2)

**Goal**: 适配器驱动 `Command(resume=...)`，区分 interrupt 前/后 effect 的重复结论。

**Independent Test**: 运行 `examples/refund/test_refund_interrupt.py` 与 `tests/integration/test_langgraph_interrupt.py`。

### Tests for User Story 4 ⚠️

- [X] T033 [P] [US4] 集成测试 `tests/integration/test_langgraph_interrupt.py`：interrupt 前有 effect 恢复后重复、interrupt 后有 effect 恢复后不重复、`resume_interrupt` 需前次 INTERRUPTED 否则抛 `ScenarioConfigError`

### Implementation for User Story 4

- [X] T034 [US4] 在 `src/agentreplayguard/adapters/langgraph.py` 补充 `resume_interrupt`（`Command(resume=...)`）与 `interrupts` 提取
- [X] T035 [US4] 编写 `examples/refund/test_refund_interrupt.py`：两个场景（effect 在 interrupt 前/后）

**Checkpoint**: US1–US4 均可独立验证。

---

## Phase 7: User Story 5 — 用业务不变量描述「应该发生什么」 (Priority: P2)

**Goal**: 用户用 `MaxEffectCount` 与 `CustomInvariant` 声明业务期望，失败报告含期望/实际值。

**Independent Test**: 运行 `tests/unit/test_invariants.py`（已覆盖）与一个自定义 predicate 示例。

### Tests for User Story 5 ⚠️

- [X] T036 [P] [US5] 补充 `tests/unit/test_invariants_custom.py`：`CustomInvariant` 通过/失败/抛异常三态、`MaxEffectCount` 边界（max_count=0）

### Implementation for User Story 5

- [X] T037 [US5] 编写 `examples/refund/test_refund_invariants.py`：`MaxEffectCount("refund", 1)` 与自定义 predicate 的通过/失败用例

**Checkpoint**: US1–US5 均可独立验证。

---

## Phase 8: User Story 6 — 在 CI 中稳定、快速地回归 (Priority: P3)

**Goal**: 确定性（20 次一致）与断网运行，单场景 <5 秒。

**Independent Test**: 运行 `tests/integration/test_determinism_and_offline.py`。

### Tests for User Story 6 ⚠️

- [X] T038 [P] [US6] 集成测试 `tests/integration/test_determinism_and_offline.py`：同 seed 20 次一致、不同 seed 行为、断网运行、无真实 sleep

### Implementation for User Story 6

- [X] T039 [US6] 实现 pytest 插件 `src/agentreplayguard/pytest_plugin.py`（`replayguard` fixture，pytest11 entry point）及契约测试 `tests/contract/test_pytest_plugin.py`
- [X] T040 [P] [US6] 确认 `pyproject.toml` 中 `[project.entry-points.pytest11]` 与 `[project.optional-dependencies]` 正确（langgraph extra）

**Checkpoint**: US1–US6 全部独立验证。

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: 影响多个故事的收尾工作。

- [X] T041 [P] 运行 `specs/001-effect-safety-testing/quickstart.md` 全流程验证（安装→全部示例→覆盖率→ruff/mypy）
- [X] T042 [P] 验证核心模块行覆盖率 ≥90%（`coverage run -m pytest && coverage report`）
- [X] T043 [P] 校验 `tests/integration/test_langgraph_retry.py` 覆盖「默认 retry_on 不重试 OSError」与「显式 retry_on 重试」两组行为
- [X] T044 [P] 完善 `docs/quickstart.md` 与 README 的用户接入说明（引用 contracts 与 quickstart.md，不重复实现细节）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖，立即开始
- **Foundational (Phase 2)**: 依赖 Setup，阻塞全部用户故事
- **US1–US6 (Phase 3–8)**: 依赖 Foundational 完成
- **Polish (Phase 9)**: 依赖全部目标故事完成

### User Story Dependencies

- **US1 (P1)**: 仅依赖 Foundational；是 MVP 核心闭环
- **US2 (P1)**: 依赖 US1（复用 guard/scenario/refund）；依赖 Foundational 的 effects 去重口径
- **US3 (P1)**: 依赖 US1（复用场景）+ Foundational；引入 adapter
- **US4 (P2)**: 依赖 US3（adapter 的 resume 基础）
- **US5 (P2)**: 依赖 Foundational（invariants）；与 US1–US4 正交
- **US6 (P3)**: 依赖 US1（确定性基础）+ US3（集成）；引入 pytest 插件

### Within Each User Story

- 测试先写且失败，再实现
- 模型/基础模块先于服务/集成
- 故事完整独立验证后再进入下一优先级

### Parallel Opportunities

- Phase 1/2 中标记 [P] 的任务可并行
- Foundational 完成后，US1 与 US5（不变量）可并行（正交模块）
- 每个故事内测试任务可并行
- US3 与 US5 可并行（adapter 与不变量正交）

---

## Parallel Example: Foundational Phase

```bash
# 并行启动基础模块测试（各自独立文件）：
Task: "T005 编写异常体系测试 tests/unit/test_errors.py"
Task: "T007 编写时钟测试 tests/unit/test_clock.py"
Task: "T009 编写 effect 存储测试 tests/unit/test_effects.py"
Task: "T011 编写故障模型测试 tests/unit/test_faults.py"
Task: "T013 编写不变量测试 tests/unit/test_invariants.py"
Task: "T015 编写报告测试 tests/unit/test_report.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 1 Setup + Phase 2 Foundational
2. 完成 Phase 3 US1（guard + scenario + refund + lost-ack 示例）
3. **STOP and VALIDATE**: `pytest examples/refund/test_refund_lost_ack.py` 通过，报告可读
4. 即得到可演示的 MVP 闭环

### Incremental Delivery

1. Setup + Foundational → 基础就绪
2. + US1 → 复现重复退款（MVP！）
3. + US2 → 验证幂等键修复
4. + US3 → checkpoint 恢复
5. + US4 → interrupt 重放
6. + US5 → 业务不变量
7. + US6 → 确定性/离线/CI
8. + Polish → 覆盖率/文档收尾

### 单开发者顺序（个人开发）

按优先级串行推进：US1 → US2 → US3 → US4 → US5 → US6；US5 可在 US1 完成后提前并行插入。

---

## Notes

- [P] 任务 = 不同文件、无依赖；[Story] 标签映射到 spec.md 用户故事
- 每个故事独立可完成、可测试；测试先写并确认失败后再实现
- 每个任务或逻辑组后提交一次
- 关键契约（`retry_on`、去重口径、片段级 checkpoint 归属）见 contracts 与 research.md，实现不得偏离
- 避免：模糊任务、同文件冲突、破坏故事独立性的跨故事依赖
