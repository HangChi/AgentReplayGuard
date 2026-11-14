# Feature Specification: 场景自动断言（消除静默漏报）

**Feature Branch**: `013-auto-assert-scenario`

**Created**: 2026-11-14

**Status**: Draft

**Input**: User description: "继续下一个特性"（agent 依据实测缺陷提出，见 research.md R-01/R-02）

## 背景与问题

AgentReplayGuard 的全部价值是「有重复副作用就让测试失败」。但当前 API 把「是否断言」交给
调用方的记忆力，导致三种**静默漏报**（已实测，见 research.md R-01）：

1. 用户造了场景、触发了重复退款，但**忘记调用 `finish()`** → 测试 **passed**。
2. 用户调了 `finish()` 但**没有断言**返回值 → 测试 **passed**。
3. 用户声明了场景与不变量，但**根本没跑** → 测试 **passed**。

项目自身数据佐证（research.md R-02）：全仓 80 次 `finish()` 仅 6 次配 `assert_clean()`，
93% 的场景不做自动断言。

对测试工具而言，「该失败却通过」比「报错」危险得多：用户会误以为自己已经守住了副作用安全。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 忘记断言时测试自动失败 (Priority: P1)

用户用 `replayguard` fixture 造了场景、跑了业务流程，但忘记调用 `finish()` 或忘记断言。
测试结束时工具自动检查该场景，若有副作用违规则测试失败并给出定位信息。

**Why this priority**: 这是本特性的唯一核心价值。没有它，产品在最关键处会静默失效。

**Independent Test**: 写一个只触发重复副作用、不做任何断言的测试，断言它**必须失败**。

**Acceptance Scenarios**:

1. **Given** 场景注入 lost-ack 且发生 2 笔重复退款，**When** 测试体不调用 `finish()`，
   **Then** 测试失败，且错误信息包含业务键、提交次数与 effect 定位。
2. **Given** 同上，**When** 测试体调用了 `finish()` 但未断言，**Then** 测试仍然失败。
3. **Given** 场景无任何违规，**When** 测试体不做断言，**Then** 测试通过（不产生误报）。

---

### User Story 2 - 显式断言与自动断言不冲突 (Priority: P1)

用户希望主动检查违规细节（如 `assert not report.ok`、`committed_count == 2`）。自动断言
不得与之冲突，也不得因用户已断言而重复报错。

**Why this priority**: 现有 33 个测试文件用手写断言；若不兼容，升级即大面积破坏。

**Independent Test**: 写一个既有手写断言、又触发违规的测试，断言它失败**且只报一次错**。

**Acceptance Scenarios**:

1. **Given** 测试体已 `report = scenario.finish(); assert not report.ok`，**When** 场景有违规，
   **Then** 测试失败，且不出现「重复报错」的叠加噪音。
2. **Given** 用户显式标记「本场景预期违规」，**When** 场景确有违规，**Then** 测试通过
   （用于「验证工具能抓到问题」的元测试）。

---

### User Story 3 - 测试体已失败时不叠加噪音 (Priority: P2)

用户的业务断言先失败了（如 `assert 1 == 2`），此时副作用检查不应再额外抛一个 ERROR 把报告
搅乱，而应把副作用结论作为**附加诊断**呈现。

**Why this priority**: 直接影响可读性；不处理会让用户以为有两个独立问题。

**Independent Test**: 写一个业务断言失败且场景有违规的测试，断言失败原因清晰、不出现
「1 failed + 1 error」的误导性叠加。

**Acceptance Scenarios**:

1. **Given** 测试体业务断言失败，**When** 场景同时有副作用违规，**Then** 报告以业务失败
   为主，副作用违规作为附加信息呈现。

---

### Edge Cases

- **场景被使用但未产生任何 effect**：应通过（可能是合法场景），但可给 warning。
- **场景声明了但完全没用**：不应静默通过而不留痕迹；至少在报告中提示「场景未运行」。
- **同一测试内创建多个场景**：每个都需被检查。
- **fixture 被参数化复用**：每个测试实例独立检查，互不干扰。
- **测试被 skip / xfail**：不应因自动断言而改变 skip/xfail 语义。
- **`Scenario` 直接构造（不走 fixture）**：自动断言不生效，但必须在文档中明确说明。

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `replayguard` fixture MUST 在测试结束后自动检查该测试创建的所有场景。
- **FR-002**: 自动检查 MUST 在场景有违规时让测试失败，失败信息 MUST 复用
  `ScenarioReport.format()` 的定位内容（effect 类型、业务键、尝试序号、提交状态）。
- **FR-003**: 自动检查 MUST NOT 因用户已显式断言而重复报错（避免噪音叠加）。
- **FR-004**: 测试体本身已失败时，自动检查 MUST NOT 追加第二个错误；副作用结论以附加
  诊断形式呈现。
- **FR-005**: MUST 提供显式「本场景预期违规」的声明方式，使「验证工具能抓到问题」的
  元测试可写。
- **FR-006**: `Scenario` 直接构造的既有用法 MUST 保持完全不变（不自动断言、行为向后兼容）。
- **FR-007**: skip / xfail 语义 MUST 不受影响。
- **FR-008**: 不新增第三方依赖；核心包仍只依赖标准库（pytest 是测试期依赖，已在
  `pytest11` entry point 中）。

### Key Entities

- **replayguard fixture**：pytest 集成入口，改为管理场景生命周期（创建登记 + 结束检查）。
- **ScenarioReport**：既有报告对象，提供 `ok` / `format()` / `violations`，作为判定依据。
- **「预期违规」声明**：新增的用户意图表达（形式待 plan 决定，候选：fixture 参数 /
  上下文管理器 / 标记）。

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: research.md R-01 的三个静默漏报探针（P1/P2/P3）在修复后**全部失败**。
- **SC-002**: 既有 001–012 全部测试无回归（当前 288 passed + 1 xfailed）。
- **SC-003**: 不产生「重复报错」：一个测试最多因副作用问题失败一次。
- **SC-004**: 测试体已失败时不出现额外的 error 条目。
- **SC-005**: 核心模块覆盖率 ≥90%；新增代码行覆盖率 ≥90%。

---

## Out of Scope

- **自动修复幂等性 / 自动改写用户图**：001 起即排除。
- **把自动断言做进 `Scenario` 构造函数**（即直接 `Scenario(...)` 也自动断言）：会破坏
  既有 80 处用法与「finish 只产出报告」语义，明确不做。
- **全局 autouse fixture 扫描所有测试**：违反「插件不执行全局补丁」的既有约定。
- **报告平台 / Web UI / 遥测**：违反宪法 III 与产品定位。

---

## Assumptions

- 用户通过 `replayguard` fixture 使用本工具是推荐路径（quickstart 已如此展示）。
- pytest fixture teardown 是合适的接入点（research R-03 已验证其行为）。
- 现有手写断言（`assert not report.ok`）的测试会与自动断言并存，需保证不重复报错。
