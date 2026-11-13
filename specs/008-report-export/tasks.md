---
description: "Task list for 008 report export"
---

# Tasks: 报告结构化导出

**Input**: Design documents from `/specs/008-report-export/`

**Tests**: 测试先行是强制要求（宪法第 IV 条）。

---

## Phase 0: 前置与基线（Setup）

- [x] T001 `pyproject.toml` 版本 bump 到 0.8.0
- [x] T002 运行基线：`pytest -q`、`ruff check .`、`mypy src/agentreplayguard`、`coverage
  --fail-under=90`，记录全绿

---

## Phase 1: 报告导出（Priority: P1）🎯

- [x] T003 [P] 编写 `tests/unit/test_report_export.py`：`to_dict()` 返回可 JSON 序列化 dict
  （Enum 转 value、fault None 保留）；`to_json()` 可 `json.loads` 解析且与 to_dict 一致；空
  报告不报错；同 seed 两次 to_json 逐字节一致；format()/assert_clean() 行为不变
- [x] T004 在 `src/agentreplayguard/report.py` 实现 `ScenarioReport.to_dict()` 与
  `to_json()`，含 `_to_plain` 递归转换（dataclass → dict、Enum → value、tuple → list）

---

## Phase 2: 文档与全量验证（Docs & Verification）

- [x] T005 [P] 更新 `docs/quickstart.md`：报告导出用法
- [x] T006 [P] 更新 `README.md`：能力清单 + 路线图勾选 008
- [x] T007 全流程：`pytest tests examples`、`ruff check .`、`mypy src/agentreplayguard`、
  `coverage report --fail-under=90`，核对 001–007 无回归

---

## Notes

- **纯转换**：to_dict/to_json 无 I/O、无依赖、无状态变更。
- **确定性**：字段顺序由 dataclass 声明序决定，to_json 用 sort_keys 双保险。
