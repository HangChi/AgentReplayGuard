---
description: "Task list for 011 junit report"
---

# Tasks: CI 报告格式（JUnit XML）

**Input**: Design documents from `/specs/011-junit-report/`

**Tests**: 测试先行是强制要求（宪法第 IV 条）。

---

## Phase 0: 前置与基线（Setup）

- [ ] T001 `pyproject.toml` 版本 bump 到 0.11.0
- [ ] T002 运行基线：`pytest -q`、`ruff check .`、`mypy src/agentreplayguard`、`coverage
  --fail-under=90`，记录全绿

---

## Phase 1: JUnit XML 导出 (Priority: P1) 🎯

- [ ] T003 [P] 编写 `tests/unit/test_junit_report.py`：violation → failure testcase 映射；
  无 violation → 通过 testcase；XML 可被解析；特殊字符转义；确定性（time=0.0，两次一致）；
  tests/failures 计数正确
- [ ] T004 实现 `src/agentreplayguard/junit.py`（`to_junit_xml(report) -> str`，标准库
  `xml.etree.ElementTree`），并在 `ScenarioReport` 加 `to_junit_xml()` 方法委托

---

## Phase 2: 文档与全量验证（Docs & Verification）

- [ ] T005 [P] 更新 `docs/quickstart.md`：JUnit 导出用法（含 CI 集成示例）
- [ ] T006 [P] 更新 `README.md`：能力清单 + 路线图勾选 011
- [ ] T007 全流程：`pytest tests examples`、`ruff check .`、`mypy src/agentreplayguard`、
  `coverage report --fail-under=90`，核对 001–010 无回归

---

## Notes

- **确定性**：`time="0.0"` 固定，不引入 wall clock（宪法第 II 条）。
- **仅标准库**：用 `xml.etree.ElementTree`，不新增依赖（宪法依赖策略）。
- **单 report → 单 testsuite**：多场景聚合由调用方负责（YAGNI）。
