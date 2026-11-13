# Implementation Plan: 多框架工具副作用记账

**Branch**: `007-multi-framework-tools` | **Date**: 2026-11-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-multi-framework-tools/spec.md`

## Summary

本特性**几乎不新增产品代码**——核心结论是「用现有 `guard.effect()` 装饰工具函数即可完成多框架
副作用记账」（research R-01）。交付物是：① 多框架接入文档（quickstart 章节）；② OpenAI
Agents SDK 的可运行 scripted 示例（官方 `ScriptedModel` 离线设施）；③ CrewAI/AutoGen 接入
说明。不写完整框架适配器（宪法第 VII 条 YAGNI）。

## Technical Context

**Language/Version**: Python ≥ 3.10

**Primary Dependencies**: 核心运行时仅标准库，无新增。示例可选依赖 `openai-agents`（仅示例
用，标记 skip-if-not-installed，不进入核心 dev extra）。

**Storage**: 复用进程内 Effect Store。

**Testing**: pytest；OpenAI Agents SDK 示例用官方 `ScriptedModel` 离线跑，无真实 LLM。

**Constraints**: 断网可运行；核心包导入不因缺任何框架失败；覆盖率 ≥90%

**Scale/Scope**: 新增 `examples/multi_framework/` 示例 + 文档；核心 `src/` 无改动（复用
guard.effect）

## Constitution Check

| 原则 | 结论 | 说明 |
|------|------|------|
| I. 真实需求优先 | PASS | 三个框架广泛使用；工具函数副作用检测是空白；接缝就在工具函数 |
| II. 确定性可复现 | PASS | ScriptedModel + guard.effect 复用 seed/逻辑时钟 |
| III. 默认模拟外部服务 | PASS | ScriptedModel 离线；无真实 LLM |
| IV. 测试先行 | PASS | 先写工具函数级测试 |
| V. 小接口面与显式契约 | PASS | 无新增公开 API（复用 guard.effect） |
| VI. 模块化与可替换边界 | PASS | 工具函数是纯 callable，天然边界 |
| VII. 克制范围（YAGNI） | PASS | 明确不做完整适配器（R-01/R-05） |
| VIII. 失败可解释 | PASS | 复用账本报告 |

**Gate result**: 全部通过。

## 设计要点

### 1. 装饰器叠加顺序

`guard.effect` 用 `functools.wraps` 保留签名。与框架 `@tool` 叠加时，推荐 **`@tool` 在内、
`@guard.effect` 在外**（或反过来需实测）：目标是让框架看到原始签名（生成工具 schema），
而 guard 在调用时拦截。文档需给出一致推荐并实测验证。

### 2. 示例结构

```
examples/multi_framework/
├── test_tool_guard.py        # 框架无关：guard.effect 装饰 callable 的记账/故障（同步+异步）
├── test_openai_agents_sdk.py # OpenAI Agents SDK scripted 示例（skip-if-not-installed）
└── README.md                 # CrewAI / AutoGen 接入说明
```

### 3. 可选依赖隔离

`openai-agents` 仅示例用，用 `pytest.importorskip` 守卫，不进 `dev` extra（避免核心 CI 引入
重依赖）。文档说明 `pip install openai-agents` 后可跑。

## 阶段划分

1. **Phase 0 前置**：版本 bump 0.7.0，基线
2. **Phase 1 US1**：框架无关工具函数级测试（guard.effect 装饰 callable）
3. **Phase 2 US2**：OpenAI Agents SDK scripted 示例
4. **Phase 3 US3**：CrewAI/AutoGen 接入文档
5. **Phase 4 文档**：quickstart + README
6. **Phase 5 全量验证**
