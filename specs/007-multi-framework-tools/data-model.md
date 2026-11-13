# Data Model: 多框架工具副作用记账

**Feature**: 007-multi-framework-tools

本特性**不新增、不修改任何数据结构**。完全复用 001 已定义的 `EffectRecord`、`EffectStore`、
`EffectGuard`、不变量与 `Scenario`。

## 明确不做变更

- 无新字段、无新实体、无新存储。
- 工具函数是普通 Python callable，`guard.effect()` 装饰即可复用全部记账/故障/检测能力。
- 不引入框架运行时语义（handoff/guardrail/memory 等）到账本模型。
