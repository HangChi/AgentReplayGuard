---
description: "Task list for 013 auto-assert-scenario"
---

# Tasks: 场景自动断言（消除静默漏报）

**Input**: Design documents from `/specs/013-auto-assert-scenario/`

**Tests**: 测试先行是强制要求（宪法第 IV 条）。

---

## Phase 0: 前置与基线（Setup）

- [x] T001 `pyproject.toml` 版本 bump 到 0.13.0
- [x] T002 运行基线：`pytest tests examples`、`ruff check .`、`mypy src/agentreplayguard`、
  `coverage --fail-under=90`，记录全绿（当前 288 passed + 1 xfailed）

---

## Phase 1: 自动断言核心（Priority: P1）🎯

- [x] T003 编写 `tests/unit/test_auto_assert.py`（先失败）：覆盖 research R-01 的三个
  漏报探针（忘记 finish / finish 不断言 / 场景未使用），断言它们**必须失败**
- [x] T004 实现 `pytest_plugin.py`：`replayguard` fixture 改为登记 + teardown 检查
  （`EffectSafetyError(report.format())`），并支持 `expect_violations=True`
- [x] T005 实现 teardown 判定顺序：测试体已失败时降级为 warning（FR-004），
  避免「1 failed + 1 error」噪音
- [x] T006 实现 skip / xfail 兼容（FR-007）：`rep_call.skipped` 或 `wasxfail` 时跳过检查
- [x] T007 实现「场景未运行」warning（Edge Case）：创建但 0 条 effect 时提示

---

## Phase 2: 契约兼容与文档（Compatibility & Docs）

- [x] T008 更新 `tests/contract/test_pytest_plugin.py`：`replayguard is Scenario` 改为
  「调用后返回 Scenario 实例」；补「同一测试多场景都检查」用例
- [x] T009 [P] 更新 `docs/quickstart.md`：说明 `replayguard` fixture 自动断言、
  `expect_violations` 用法、以及直接 `Scenario(...)` 不自动断言的差异
- [x] T010 [P] 更新 `README.md` 与 `CHANGELOG.md`：记录 0.13.0 的 Changed（fixture 形态）
- [x] T011 [P] 更新 `examples/refund/test_refund_lost_ack.py`：展示自动断言用法
  （去掉手写 `assert not report.ok` 也能失败的示例）

---

## Phase 3: 全量验证（Verification）

- [x] T012 全流程：`pytest tests examples`、`ruff check .`、`mypy src/agentreplayguard`、
  `coverage report --fail-under=90`，核对 001–012 无回归
- [x] T013 回归验证：确认既有 33 个手写断言的测试文件**不出现重复报错**

---

## Notes

- **不碰核心模块**：`scenario.py` / `effects.py` / `invariants.py` 一行不改（宪法 VI）。
- **可感知变更**：`replayguard is Scenario` 契约失效 → 必须记录迁移说明（plan 中 V 的处理）。
- **克制**：不做全局 autouse fixture，不做自动修复（YAGNI）。
