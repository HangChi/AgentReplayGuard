---
description: "Task list for 010 sync stream"
---

# Tasks: 同步 stream 入口（LangGraphAdapter）

**Input**: Design documents from `/specs/010-sync-stream/`

**Tests**: 测试先行是强制要求（宪法第 IV 条）。

---

## Phase 0: 前置与基线（Setup）

- [x] T001 `pyproject.toml` 版本 bump 到 0.10.0
- [x] T002 运行基线：`pytest -q`、`ruff check .`、`mypy src/agentreplayguard`、`coverage
  --fail-under=90`，记录全绿

---

## Phase 1: 同步 stream 入口 (Priority: P1) 🎯

- [x] T003 [P] 编写 `tests/integration/test_streaming.py` 扩展 + `tests/unit/test_adapter_stream.py`
  扩展：`stream()` 遍历产出 chunk；effect run_id/branch_id 归属正确；`finish()` RunSegment
  结构正确；中途异常记录 error_type 并传播；break 正常收尾；`stream_mode` 透传
- [x] T004 实现 `LangGraphAdapter.stream()` 同步生成器（`_begin_run` 首次迭代前、`finally
  _finish_run`），不要求 `ainvoke`

---

## Phase 2: 文档与全量验证（Docs & Verification）

- [x] T005 [P] 更新 `docs/quickstart.md`：同步 stream 用法
- [x] T006 [P] 更新 `README.md`：能力清单 + 路线图勾选 010
- [x] T007 全流程：`pytest tests examples`、`ruff check .`、`mypy src/agentreplayguard`、
  `coverage report --fail-under=90`，核对 001–009 无回归

---

## Notes

- **同步生成器 + finally 收尾**：`stream()` 是同步生成器，`_begin_run` 首次迭代前、`_finish_run`
  在 `finally` 中，保证正常/异常/break 三条路径收尾。
- **不要求 ainvoke**：同步 stream 底层用 `invoke` 驱动，不做 `_ensure_async_capable` 检查。
- **stream_events 不做**：v2 不支持、v3 实验性（research R-03）。
