# Tasks: HTTP 故障注入传输层

**Input**: Design documents from `/specs/003-http-fault-transport/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/http-transport-api.md

**Tests**: 本特性采用测试先行（宪法原则 IV），每个用户故事先写失败测试再实现。

**Organization**: 任务按用户故事分组；US1/US2 为 P1，US3/US4 为 P2。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无未完成依赖）
- **[Story]**: 所属用户故事（US1–US4）
- 所有任务包含精确文件路径

## Path Conventions

单包项目：`src/agentreplayguard/`、`tests/`、`examples/refund/`、`docs/`。

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 可选依赖与版本元数据

- [ ] T001 Add optional extra and dev dependency for httpx; bump version to 0.3.0 in `pyproject.toml`, then run `uv lock` and `uv sync --extra dev --extra httpx` to refresh `uv.lock`

**Checkpoint**: `uv run python -c "import httpx"` 成功，核心包仍无新增必选依赖。

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 两个传输层共享的数据结构与故障映射基础

**⚠️ CRITICAL**: US1–US4 均依赖本阶段

- [ ] T002 [P] Write failing tests for `HttpEffect` validation, optional-import isolation, and core-package import behavior in `tests/unit/test_http_effect.py` and `tests/contract/test_http_public_api.py`
- [ ] T003 Implement module skeleton in `src/agentreplayguard/adapters/httpx.py`: actionable `ImportError` when httpx is missing, frozen `HttpEffect` dataclass with field validation, `ClassifyRequest` type alias, and `_map_injected_fault(record, request)` helper covering all five `FaultKind` values

**Checkpoint**: `HttpEffect` 可构造并校验；未匹配/映射辅助函数可被单元测试直接调用。

---

## Phase 3: User Story 1 - 用真实同步 HTTP 客户端复现 lost-ack (Priority: P1) 🎯 MVP

**Goal**: `FaultyTransport` 包裹底层同步 transport，复用 guard 记账并在正确阶段注入故障。

**Independent Test**: `uv run pytest tests/unit/test_http_transport.py -q` 覆盖正常提交、lost-ack 重试、提交前失败与底层异常传播。

### Tests for User Story 1 ⚠️

> 先写测试并确认失败

- [ ] T004 [P] [US1] Write failing sync transport tests in `tests/unit/test_http_transport.py`: normal classified request records one `committed`, lost-ack retry records two `committed` with attempts 1/2, before-commit fault raises `httpx.ConnectTimeout` without calling base, base exception records `not_committed` and propagates unchanged, `close()` delegates to base

### Implementation for User Story 1

- [ ] T005 [US1] Implement `FaultyTransport(httpx.BaseTransport)` in `src/agentreplayguard/adapters/httpx.py`: classify request, call `scenario.guard().call` for matched requests, pass through unmatched, translate guard faults via `_map_injected_fault`, delegate `close()`

**Checkpoint**: US1 独立可用；同步客户端零业务改动即可复现 lost-ack。

---

## Phase 4: User Story 2 - 异步 HTTP 客户端同样可注入 (Priority: P1)

**Goal**: `AsyncFaultyTransport` 与同步版语义一致，支持取消。

**Independent Test**: `uv run pytest tests/unit/test_http_transport_async.py -q`，并断言同步/异步等价场景记录一致。

### Tests for User Story 2 ⚠️

- [ ] T006 [P] [US2] Write failing async transport tests in `tests/unit/test_http_transport_async.py`: normal request, lost-ack retry, cancellation records `unknown` and propagates `CancelledError`, base exception propagation, `aclose()` delegation, sync/async parity of records/status/attempt

### Implementation for User Story 2

- [ ] T007 [US2] Implement `AsyncFaultyTransport(httpx.AsyncBaseTransport)` in `src/agentreplayguard/adapters/httpx.py`: `await scenario.guard().acall` for matched requests, pass through unmatched, translate faults, delegate `aclose()`

**Checkpoint**: 同步与异步 API 均可独立演示 lost-ack。

---

## Phase 5: User Story 3 - 业务键与幂等键从请求中提取 (Priority: P2)

**Goal**: 分类回调把请求映射为 effect 语义；未匹配请求透传且不消耗故障计划；配置错误快速失败。

**Independent Test**: `uv run pytest tests/unit/test_http_transport.py -k "classify or passthrough or invalid" -q`。

### Tests for User Story 3 ⚠️

- [ ] T008 [P] [US3] Write failing classification tests in `tests/unit/test_http_transport.py`: extract business key from JSON body, extract idempotency key from header and JSON field, unmatched GET passes through with zero records and no fault-plan consumption, classify raising wraps into `ScenarioConfigError` without calling base, non-`HttpEffect` return rejected, empty business key and non-serializable params fail fast

### Implementation for User Story 3

- [ ] T009 [US3] Add shared `_classify_or_raise` and request-binding helpers in `src/agentreplayguard/adapters/httpx.py`, wire both transports to use them, and ensure `params`/`idempotency_key` flow through `EffectGuard` hashing unchanged

**Checkpoint**: 读写区分与提取策略可用；误配置不会发出请求。

---

## Phase 6: User Story 4 - 故障映射为客户端可识别的异常 (Priority: P2)

**Goal**: 五类故障全部映射为 httpx 标准异常，并保留原始 request 与 `__cause__`。

**Independent Test**: `uv run pytest tests/unit/test_http_transport.py -k "fault_mapping" -q`。

### Tests for User Story 4 ⚠️

- [ ] T010 [P] [US4] Write failing fault-mapping tests in `tests/unit/test_http_transport.py`: timeout-before → `ConnectTimeout`, timeout-after → `ReadTimeout`, reset → `ConnectError`, server-error → `HTTPStatusError` with status 500, partial-success → `ReadError`; every mapped exception carries the original request and a `TimeoutError`/`ServiceError`/`PartialSuccessError` `__cause__`

### Implementation for User Story 4

- [ ] T011 [US4] Refine `_map_injected_fault` and its call sites in `src/agentreplayguard/adapters/httpx.py` so only records with `fault is not None` are translated and all other exceptions propagate unchanged

**Checkpoint**: 业务重试逻辑按客户端异常类型即可命中。

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: 示例、契约、文档与全量验证

- [ ] T012 [P] Add `examples/refund/http_tools.py` and `examples/refund/test_refund_http.py`: in-process `httpx.MockTransport` refund service, classify function (JSON body + `Idempotency-Key`), sync and async lost-ack duplicate detection, and idempotent-key scenario passing
- [ ] T013 [P] Extend `tests/contract/test_http_public_api.py`: assert public signatures, core import does not load the adapter, and a simulated missing-httpx subprocess shows the actionable `ImportError`
- [ ] T014 [P] Update `README.md` and `docs/quickstart.md` with HTTP transport usage, supported httpx range, commit boundary (response headers), and installation command
- [ ] T015 Run full verification: `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src/agentreplayguard`, `uv run coverage run -m pytest -q && uv run coverage report --fail-under=90`; fix all failures and mark tasks complete

**Checkpoint**: 全部质量闸门通过，示例与文档可运行。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖，立即开始
- **Foundational (Phase 2)**: 依赖 Setup；阻塞全部用户故事
- **User Stories (Phase 3–6)**: 均依赖 Phase 2
  - US1 与 US2 可并行（不同测试文件；实现同文件需顺序写入）
  - US3/US4 依赖 US1 的实现骨架；可在 US1 完成后并行
- **Polish (Phase 7)**: 依赖 US1–US4 完成

### User Story Dependencies

- **US1 (P1)**: Phase 2 完成后可开始，无其他故事依赖
- **US2 (P1)**: Phase 2 完成后可开始；与 US1 共享 `_map_injected_fault`
- **US3 (P2)**: 依赖 US1/US2 的请求入口存在，用于分类与透传验证
- **US4 (P2)**: 依赖 US1/US2 的异常处理入口存在，用于五类映射验证

### Within Each User Story

- 测试先行并确认失败，再实现
- 共享 helper 先于 transport 接线
- 每个故事完成后运行该故事的独立测试

### Parallel Opportunities

- T001 独立
- T002 与 T003 为测试/实现串行对
- T004 与 T006 可在 Phase 2 后并行编写（不同文件）
- T008 与 T010 可并行编写（同文件不同测试函数，建议顺序写入避免冲突）
- T012/T013/T014 可并行

---

## Parallel Example: User Story 1

```bash
# 测试先行：
uv run pytest tests/unit/test_http_transport.py -q   # 预期失败（模块/类不存在）
# 实现后：
uv run pytest tests/unit/test_http_transport.py -q   # 预期通过
```

## Parallel Example: User Story 2

```bash
uv run pytest tests/unit/test_http_transport_async.py -q
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 1 + Phase 2
2. 完成 US1（T004–T005）
3. 运行 `uv run pytest tests/unit/test_http_transport.py -q` 独立验收
4. 此时已可在真实同步 httpx 客户端上复现 lost-ack

### Incremental Delivery

1. Setup + Foundational → 基础就绪
2. US1 → 同步 MVP
3. US2 → 异步对等
4. US3 → 提取与安全边界
5. US4 → 完整异常映射
6. Polish → 示例、契约、文档与质量闸门

---

## Notes

- 所有测试与示例使用 `httpx.MockTransport`，禁止真实网络与真实延迟
- 实现集中在 `src/agentreplayguard/adapters/httpx.py`，核心模块不 import httpx
- 每个任务完成后可按需提交；本特性最终以单个实现提交收尾
- 覆盖率统计包含新增适配模块，目标 ≥90%
