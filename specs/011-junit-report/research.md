# Research: CI 报告格式（JUnit XML）

**Feature**: 011-junit-report
**Status**: Implemented

## R-01 竞品缺口：pytest --junitxml 记录的是 pytest 用例，不是副作用检测结论

**决策**：本特性提供「副作用安全检测」的 JUnit XML，与 pytest 自带的 `--junitxml` 正交。

**依据**：pytest 的 `--junitxml` 记录的是「pytest 测试用例」的 pass/fail（每个 `test_*` 函数
一个 testcase）。而 AgentReplayGuard 的检测结论是「场景的副作用违规」（一个 scenario 可能
产生多个 violation，或 violation 与 pytest 用例的 pass/fail 无关——用户可能在测试里只做
`finish()` 记录而不断言）。CI 需要的是「副作用安全检测」作为独立结构化产物，而非「某个
pytest 函数是否 pass」。

## R-02 JUnit XML 是 de-facto 标准，全 CI 原生解析

**决策**：采用 JUnit XML（JUnit 4 风格），GitLab / GitHub Actions / Jenkins / Azure DevOps
原生解析。

**依据（检索确认）**：
- 结构：`testsuites`（根，可选）→ `testsuite`（name/tests/failures/errors/time）→
  `testcase`（name/classname/time）→ `failure`（message/type，内容为详情）。
- GitLab 解析 `testsuite.name`、`testcase.classname/name/file/time`、`failure/error/skipped`
  内容（见 GitLab 单元测试报告文档）。
- 无官方唯一 schema，属「兼容的 de-facto 格式家族」，各 CI 对 `testsuite`/`testcase`/
  `failure` 的核心元素兼容。

## R-03 映射语义：scenario → testsuite，violation → testcase

**决策**：
- 一个 `ScenarioReport` → 一个 `<testsuite name=scenario_name>`。
- 每个 `Violation` → 一个 `<testcase name="<invariant_name>">`，内含 `<failure
  message=violation.message type=invariant_name>`（详情为 effect 列表）。
- 无 violation（`ok`）→ 一个 `<testcase name="effects_safety">` 通过。

**依据**：`Violation` 字段（invariant_name/message/expected/actual/effect_ids）足够映射为
JUnit 的 failure；按 violation 拆 testcase 使 CI 能逐条显示检测失败。

## R-04 确定性：time 属性不用 wall clock

**决策**：JUnit 的 `time` 属性 MUST NOT 用 wall clock（违反宪法第 II 条确定性）。方案：固定
`time="0.0"`（本工具的「时间」是逻辑 tick，不是墙钟秒）。

**依据**：宪法第 II 条「时间、随机数、ID 生成 MUST 可注入」「测试 MUST NOT 依赖真实时钟」。
同一 seed 下 JUnit XML MUST 逐字节一致，故 `time` 固定。

## R-05 依赖：仅标准库

**决策**：用标准库 `xml.etree.ElementTree` 生成 XML（安全转义），不新增第三方依赖。

**依据**：宪法依赖策略「核心包运行时 MUST 仅依赖标准库」；JUnit XML 生成用标准库即可，
无需 lxml 等重依赖。
