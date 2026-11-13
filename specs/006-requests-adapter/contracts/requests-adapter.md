# Contract: requests 适配器

**Feature**: 006-requests-adapter

## 判定顺序

1. **分类**：`send()` 先调 `classify(request)`；返回 `None` → 透传 `base.send`，不记账不消耗故障。
2. **记账 + 故障注入**：已分类请求进入 `scenario.guard().call`（复用 attempt/哈希/故障接线）。
3. **异常映射**：guard 抛出的注入故障转换为 `requests.exceptions` 标准异常；非注入异常原样传播。
4. **提交边界**：提交前故障不调用 `base.send`；提交后故障在 `base.send` 返回后注入。
5. **close 委托**：`close()` 委托 `base.close()`。

## 行为用例表（must-have）

| # | 场景 | 期望 |
|---|------|------|
| RA-01 | 分类返回 HttpEffect 的 POST | effect 记录 1 条 committed，key 正确 |
| RA-02 | 分类返回 None 的 GET | 透传，无 effect，不消耗故障 |
| RA-03 | 分类抛异常 | `ScenarioConfigError`，不调 base |
| RA-04 | TIMEOUT_BEFORE_COMMIT | 抛 ConnectTimeout，effect not_committed，不调 base |
| RA-05 | TIMEOUT_AFTER_COMMIT | 抛 ReadTimeout，effect committed |
| RA-06 | CONNECTION_RESET | 抛 ConnectionError |
| RA-07 | SERVER_ERROR | 抛 HTTPError（500） |
| RA-08 | PARTIAL_SUCCESS | 抛 ChunkedEncodingError |
| RA-09 | base 自身抛异常 | effect not_committed，异常原样传播 |
| RA-10 | lost-ack + 重试（无幂等键） | committed_count=2，NoDuplicateEffects 报违规 |
| RA-11 | 同场景带幂等键 | committed_count=1，ok=True |
| RA-12 | close() | 委托 base.close() |

## 公开 API 变更面

- **新增**：`agentreplayguard.adapters.requests.RequestsAdapter`。
- **不变**：`HttpEffect` 从 `_http_common` 重新导出，`adapters.httpx.HttpEffect` 仍可用（向后兼容）。
- **版本**：minor bump 0.5.0 → 0.6.0。
