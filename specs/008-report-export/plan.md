# Implementation Plan: 报告结构化导出

**Branch**: `008-report-export` | **Date**: 2026-11-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-report-export/spec.md`

## Summary

给 `ScenarioReport` 增加 `to_dict()` 与 `to_json()`，把 report 转成纯 JSON 可序列化的 dict
（Enum → value，dataclass → dict），覆盖 scenario_name/seed/effects/run_segments/violations/
warnings。确定性输出（字段顺序固定、无 wall clock）。纯内存转换，无 I/O、无新依赖。

## Technical Context

**Language/Version**: Python ≥ 3.10

**Primary Dependencies**: 仅标准库（`dataclasses.asdict`、`json`），无新增。

**Storage**: 无（纯转换）。

**Testing**: pytest；验证 dict 可 JSON 序列化、JSON 可解析、确定性。

**Constraints**: 确定性；`format()`/`assert_clean()` 行为不变；覆盖率 ≥90%

**Scale/Scope**: 扩展 `report.py`（约 40 行）+ 1 个测试文件；不改其它模块

## Constitution Check

| 原则 | 结论 | 说明 |
|------|------|------|
| I. 真实需求优先 | PASS | CI 存档/审计/跨工具消费需结构化报告（R-01） |
| II. 确定性可复现 | PASS | 字段顺序固定、无 wall clock |
| III. 默认模拟外部服务 | PASS | 纯内存转换，无 I/O |
| IV. 测试先行 | PASS | 先写导出测试 |
| V. 小接口面与显式契约 | PASS | 仅新增 to_dict/to_json 两方法 |
| VI. 模块化与可替换边界 | PASS | 只改 report.py |
| VII. 克制范围（YAGNI） | PASS | 不做持久化、不做 to_file |
| VIII. 失败可解释 | PASS | 导出内容与 format 一致，含完整违规信息 |

**Gate result**: 全部通过。

## 设计要点

### 1. Enum → value 转换

`EffectStatus`/`FaultKind`/`RunInputKind` 都是 `str, Enum`，`str(x)` 即 value。用一个递归
转换函数 `_to_plain(obj)` 处理：dataclass → `asdict` 后递归；Enum → value；list/tuple → list。

### 2. 确定性

字段顺序由 dataclass 字段声明序决定（`asdict` 保持声明序）；`to_json` 用 `json.dumps(...
, ensure_ascii=False, sort_keys=True)` 保证 dict 键排序稳定（虽然 dict 已按插入序，sort_keys
双保险）。

## 阶段划分

1. **Phase 0 前置**：版本 bump 0.8.0，基线
2. **Phase 1**：to_dict/to_json 实现（测试先行）
3. **Phase 2**：文档（quickstart/README）+ 全量验证
