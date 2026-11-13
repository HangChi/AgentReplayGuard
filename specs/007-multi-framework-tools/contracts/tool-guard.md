# Contract: 多框架工具函数接入

**Feature**: 007-multi-framework-tools

## 核心契约：工具函数是唯一接缝

本特性的契约是**行为**而非新 API：任何框架的工具函数，只要用 `guard.effect()` 装饰，就复用
既有的记账/故障/不变量语义。

## 装饰器叠加顺序（must-have）

- `guard.effect` 用 `functools.wraps` 保留 `__name__`/`__doc__`/签名。
- 与框架 `@tool` 叠加时，须让框架仍能读到原始签名（用于生成工具 schema）。推荐顺序在示例中
  实测锁定，并在文档明确。

## 行为用例表（must-have）

| # | 场景 | 期望 |
|---|------|------|
| MF-01 | `guard.effect` 装饰的同步 callable 直接调用 | effect 1 条 committed，key 正确 |
| MF-02 | `guard.effect` 装饰的异步 callable `await` 调用 | effect 1 条 committed |
| MF-03 | lost-ack + 重试（无幂等键） | committed=2，NoDuplicateEffects 报违规 |
| MF-04 | 同场景带幂等键 | committed=1，ok=True |
| MF-05 | OpenAI Agents SDK scripted 工具流程 | effect 记账，无真实 LLM |
| MF-06 | 注入故障到 scripted 工具 | 故障语义正确，effect 状态正确 |

## 公开 API 变更面

- **无新增公开 API**：复用 `EffectGuard.effect`。
- **版本**：minor bump 0.6.0 → 0.7.0（新增示例与文档能力，非 API 变更；保守按 minor 记录）。
