# Data Model: requests 适配器

**Feature**: 006-requests-adapter

本特性**不新增业务数据结构**，仅做一次「抽取 + 复用」：

## 变更

- **抽取 `HttpEffect`**：从 `adapters/httpx.py` 抽取到 `adapters/_http_common.py`（仅标准库依赖），
  字段与校验逻辑不变：`effect_type`、`business_key`、`params`、`idempotency_key`。
- **复用**：`EffectRecord`、`EffectStore`、`Scenario`、`EffectGuard`、不变量全部复用，不改字段。

## 明确不做变更

- `EffectRecord` / `EffectStatus` / `FaultKind` / `RunSegment` / `ScenarioReport` 结构不变。
- `EffectStore` 查询接口不变。
- 不新增持久化、不新增存储后端。
