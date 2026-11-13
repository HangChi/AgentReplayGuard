# Research: requests 客户端的副作用记账与故障注入适配器

**Feature**: 006-requests-adapter
**Status**: Draft

## R-01 接缝：requests 官方 Transport Adapter

**决策**：用 `requests.adapters.BaseAdapter` 子类 + `Session.mount(prefix, adapter)` 作为接缝，
与 003 的 httpx transport 对称。

**依据（实测）**：子类实现 `send(request, **kwargs) -> Response` 与 `close()`，`send` 收到
`requests.PreparedRequest`（含 `method`/`url`/`body`/`headers`），可拿到与 httpx `Request`
同构的信息。`Session.mount('https://', adapter)` 按最长前缀路由。实测 POST JSON 能完整拿到
`body=b'{"refund_id": "R-1", ...}'` 与 `Content-Type: application/json` 头。

**被否决的方案**：monkey-patch `requests.Session.send`。理由：全局副作用、污染所有 Session、
无法按 URL 前缀路由，违反宪法第 V 条「显式契约」与第 VI 条「模块化边界」。

## R-02 故障异常映射

**决策**：把 FaultKind 映射为 `requests.exceptions` 标准异常，与 003 的 httpx 映射一一对应。

| FaultKind | requests 异常 |
|---|---|
| TIMEOUT_BEFORE_COMMIT | `ConnectTimeout` |
| TIMEOUT_AFTER_COMMIT | `ReadTimeout` |
| CONNECTION_RESET | `ConnectionError` |
| SERVER_ERROR | `HTTPError`（带 500 response） |
| PARTIAL_SUCCESS | `ChunkedEncodingError`（读取类异常） |

**依据**：requests 异常体系（实测 `requests.exceptions`）有 `ConnectTimeout`/`ReadTimeout`/
`ConnectionError`/`HTTPError`，与 httpx 对应。`PARTIAL_SUCCESS`（提交后部分失败）没有
`ReadError` 的完美对应，`ChunkedEncodingError` 是 requests 里最接近「读取中断」的异常。

## R-03 范围取舍：只做 requests，不做 urllib3/aiohttp

**决策**：006 只做 requests 同步适配器；urllib3 / aiohttp 本轮不做。

**依据**：
- **requests**：生态最大、官方 `BaseAdapter` 接缝干净（R-01），价值/成本比最高。
- **urllib3**：是 requests 的底层，独立使用者少；唯一接缝是全局替换
  `pool_classes_by_scheme`（hacky、进程级副作用），且 requests 适配器已覆盖其主流使用场景。
- **aiohttp**：未安装，属独立 asyncio 生态，接缝（自定义 Connector/中间件）与 requests 不同，
  价值与复杂度需单独论证。

## R-04 复用 003 的分类语义

**决策**：复用 `HttpEffect` 数据类与分类回调语义（method + url + JSON body + header 幂等键），
只是请求对象类型从 `httpx.Request` 变为 `requests.PreparedRequest`。

**依据**：`HttpEffect` 只表达「effect 语义」（effect_type/business_key/params/idempotency_key），
与具体客户端无关，可直接复用。分类回调签名因请求类型不同而独立定义为
`Callable[[requests.PreparedRequest], HttpEffect | None]`。

## R-05 竞品/现状

已有工具（responses、requests-mock、vcrpy）做请求 mock/录制，但都不做「副作用记账 +
确定性故障注入 + 重复检测」的测试语义（同 003 的调研结论）。本特性是 AgentReplayGuard
在 requests 生态上的增量。
