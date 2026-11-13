# Feature Specification: CI 报告格式（JUnit XML）

**Feature Branch**: `011-junit-report`

**Created**: 2026-11-14

**Status**: Draft

**Input**: User description: "B 类扩展，从 CI 报告格式（JUnit XML 等）开始"

## 背景与问题

008 已提供 `ScenarioReport.to_dict()` / `to_json()`（结构化导出），但这些是 JSON 格式，
CI 系统（GitLab / GitHub Actions / Jenkins / Azure DevOps）原生消费的是 **JUnit XML**。用户
若要在 CI 里把「副作用安全检测」作为结构化产物展示，需要手动把 JSON 转成 JUnit XML。

本特性新增 `to_junit_xml()`，把 `ScenarioReport` 转成 CI 原生解析的 JUnit XML：每个场景
（scenario）映射为一个 test suite，每个副作用违规（violation）映射为一个失败 test case。
与 pytest 自带的 `--junitxml`（记录 pytest 用例结果）正交——本特性输出的是「副作用安全
检测」的结论，而非「某个 pytest 函数是否 pass」。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 导出 JUnit XML (Priority: P1)

用户希望把 `ScenarioReport` 导出为 JUnit XML，供 CI 展示副作用检测失败。

**Why this priority**: 这是本特性的唯一能力，也是「CI 报告格式」的核心价值。

**Independent Test**: 一个含 violation 的报告 `to_junit_xml()` 返回格式正确的 JUnit XML，
`testsuite` 名 = scenario 名，每个 violation 一个带 `<failure>` 的 `testcase`。

**Acceptance Scenarios**:

1. **Given** 一个含 N 个 violation 的报告，**When** 调 `to_junit_xml()`，**Then** 返回的 XML
   含一个 `testsuite`（name=scenario_name、failures=N），含 N 个带 `<failure>` 的 `testcase`。
2. **Given** 一个无 violation 的报告，**When** 调 `to_junit_xml()`，**Then** 返回含一个
   通过 `testcase`（无 `<failure>`）的 XML。
3. **Given** 含特殊字符（`<`、`&`、`"`）的 violation 消息，**When** 导出，**Then** 被正确
   XML 转义（不会产生非法 XML）。

---

### Edge Cases

- **确定性**：同 seed 下 `to_junit_xml()` 逐字节一致（time 固定 0.0，不引入 wall clock）。
- **空报告**（无 effect 无 violation）：产生一个通过 testcase，不报错。
- **warning 但无 violation**：warnings 不映射为失败（仅 violation 映射为 failure），但可
  作为 suite 的 system-out 或忽略（本轮忽略，保持最小）。
- **多个场景**：每个 `ScenarioReport` 独立生成 XML；聚合多场景到一个 `testsuites` 由调用方
  决定（本轮只做单 report → 单 testsuite，YAGNI）。

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `ScenarioReport` MUST 新增 `to_junit_xml()` 方法，返回 JUnit XML 字符串
  （根元素 `testsuite`）。
- **FR-002**: 映射 MUST 为：scenario_name → `testsuite.name`；每个 violation → 一个
  `testcase`（name=invariant_name、classname=scenario_name），内含 `<failure
  message=violation.message type=invariant_name>`，详情为 effect_id 列表。
- **FR-003**: 无 violation 时 MUST 产出一个通过的 `testcase`（name="effects_safety"）。
- **FR-004**: XML 特殊字符 MUST 正确转义（用标准库 `xml.etree.ElementTree`）。
- **FR-005**: `time` 属性 MUST 固定为 `0.0`（确定性，不引入 wall clock）。
- **FR-006**: `testsuite` 的 `tests`/`failures` 计数 MUST 与 testcase/failure 数量一致。
- **FR-007**: 复用 `to_dict()`（008）或直接读 `violations`，不新增数据结构。
- **FR-008**: 不新增第三方依赖（仅标准库）；不改动 `format()`/`assert_clean()`/`to_dict()`/
  `to_json()` 行为（回归）。

### Key Entities

- **无新增数据结构**：`ScenarioReport` 增加一个方法。

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `to_junit_xml()` 返回可被 XML 解析器解析的合法 JUnit XML。
- **SC-002**: violations 数 = XML 中 `<failure>` 数 = `testsuite.failures` 属性。
- **SC-003**: 同 seed 两次 `to_junit_xml()` 逐字节一致（time=0.0）。
- **SC-004**: 特殊字符被正确转义（XML 合法）。
- **SC-005**: 核心模块覆盖率 ≥90%；既有 001–010 测试无回归。

---

## Out of Scope

- **多场景聚合到单个 `testsuites`**：本轮只做单 report → 单 testsuite（YAGNI）。
- **JUnit 之外的格式**（TAP、Cobertura、SonarQube 通用格式）：按需扩展。
- **自动写文件**（`write_junit(path)`）：调用方用 `open(path, "w").write(report.to_junit_xml())`
  即可（YAGNI）。
- **pytest 插件自动产出 JUnit**：用户手动调用 `to_junit_xml()`；pytest 集成是独立特性。
- **遥测、真实服务、Web UI**：违反宪法第 III 条，且偏离产品定位，明确不做。

---

## Assumptions

- JUnit XML（JUnit 4 风格）是 CI 原生解析的 de-facto 标准（research R-02）。
- 一个 scenario 对应一个 testsuite 是合理粒度（用户可在 CI 里聚合多场景）。
- `time` 固定 0.0 不损失信息（本工具的「时间」是逻辑 tick，非墙钟）。
