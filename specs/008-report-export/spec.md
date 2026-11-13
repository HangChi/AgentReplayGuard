# Feature Specification: 报告结构化导出

**Feature Branch**: `008-report-export`

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: "本地持久化 Effect Store 改为报告结构化导出（to_dict / to_json）"

## 背景与问题

`ScenarioReport` 目前只有 `format()`（人类可读文本）和 `assert_clean()`。用户在 CI、审计、
跨工具消费等场景下，需要**结构化**的报告（dict / JSON），而不是解析文本。

本特性给 `ScenarioReport` 增加 `to_dict()` 与 `to_json()`，导出与 `format()` 信息内容一致、
确定性（无 wall clock、字段顺序固定）的结构化报告。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 导出结构化报告 (Priority: P1)

用户希望把 `ScenarioReport` 导出为 dict / JSON，供 CI 存档、审计、跨工具消费。

**Why this priority**: 这是本特性的唯一能力，也是「报告导出」的核心价值。

**Independent Test**: 一个场景 `finish()` 后，`report.to_dict()` 返回含 effect 记录、violations、
run_segments 的 dict；`report.to_json()` 返回可解析的 JSON 字符串。

**Acceptance Scenarios**:

1. **Given** 一个含 effect 与 violation 的报告，**When** 调 `to_dict()`，**Then** 返回纯
   JSON 可序列化的 dict（Enum 转 value 字符串），含 scenario_name/seed/effects/violations/
   run_segments/warnings。
2. **Given** 同一报告，**When** 调 `to_json()`，**Then** 返回可被 `json.loads` 解析的字符串，
   与 `to_dict()` 信息一致。
3. **Given** 同 seed 连跑两次，**When** 比较两次 `to_json()`，**Then** 逐字节一致（确定性）。

---

### Edge Cases

- **空报告**（无 effect、无 violation）：`to_dict()` 返回空列表字段，不报错。
- **Enum 序列化**：`EffectStatus` / `FaultKind` / `RunInputKind` 转 value 字符串，不能是
  对象。
- **fault 为 None**：effect 无故障时 `fault` 导出为 `None`。
- **确定性**：字段顺序固定（按 EffectRecord 字段声明序），不引入 wall clock / 内存地址。

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `ScenarioReport` MUST 新增 `to_dict()`，返回纯 JSON 可序列化的 dict（Enum 转
  value，dataclass 转 dict），覆盖 scenario_name、seed、effects、run_segments、violations、
  warnings。
- **FR-002**: `ScenarioReport` MUST 新增 `to_json()`，返回 `json.dumps(to_dict(), ...)` 的
  确定性字符串（字段顺序固定、紧凑或稳定缩进）。
- **FR-003**: 导出 MUST 确定性：同一 seed 下 `to_json()` 逐字节一致（宪法第 II 条）。
- **FR-004**: `EffectRecord` / `RunSegment` / `Violation` 转 dict 时 Enum 转 value，`fault`
  等可选字段 None 原样保留。
- **FR-005**: 不改动 `format()` 与 `assert_clean()` 的现有行为（回归）。
- **FR-006**: 导出不产生任何 I/O、不引入依赖（纯内存转换，宪法第 III 条）。

### Key Entities

- **无新增数据结构**：`ScenarioReport` 增加两个方法。

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `to_dict()` 返回可被 `json.dumps` 序列化的 dict。
- **SC-002**: `to_json()` 可被 `json.loads` 解析，且与 `to_dict()` 信息一致。
- **SC-003**: 同 seed 两次 `to_json()` 逐字节一致。
- **SC-004**: 核心模块覆盖率 ≥90%；既有 001–007 测试无回归。

---

## Out of Scope

- **持久化 Effect Store**（落盘/读回、SQLite）：见 research R-01，超出「单次测试运行」定位。
- **跨进程账本共享**：001 spec 已排除，维持排除。
- **导出到文件**（`to_file(path)`）：调用方用 `open(path).write(report.to_json())` 即可，无需
  内置（YAGNI）。

---

## Assumptions

- `EffectRecord`/`RunSegment`/`Violation` 都是 dataclass，`asdict` 已能结构化。
- Enum 是 `str, Enum`（`EffectStatus`/`FaultKind`/`RunInputKind`），转 value 天然确定。
- 导出是无副作用的纯转换（宪法第 III 条）。
