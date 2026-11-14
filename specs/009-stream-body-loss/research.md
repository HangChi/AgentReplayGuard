# Research: 流式响应体丢失语义（httpx 传输层）

**Feature**: 009-stream-body-loss
**Status**: Implemented

## R-01 现状：提交边界在「响应头到达」，body 读取失败在范围外

**决策**：003 以「响应头到达」为提交边界，`handle_request` 返回 `Response` 即记 `committed`；
body 的惰性读取发生在 guard 之外，其失败无法被追踪或注入。

**依据（实测）**：
- 非流式 `client.send()` 默认读完整 body，body 失败会在 `handle_request` 内抛 → 现有 guard 能追踪。
- 流式 `client.stream()` 下，`handle_request` 返回后 effect 已 `committed`，之后 `r.read()` 的
  失败发生在 guard 之外 → 无法追踪。
- 003 spec 第 122 行明确：「本次以响应头到达作为提交边界；流式响应体读取失败的语义不在范围内」。

## R-02 故障注入机制：惰性 body 流

**决策**：`httpx.Response(content=<SyncByteStream>)` 构造惰性 body，读取时才迭代流。用
`SyncByteStream` 子类在迭代中抛 `httpx.ReadError`，即可精确模拟「响应头到达、body 丢失」。

**依据（实测）**：
```python
class BrokenStream(SyncByteStream):
    def __iter__(self):
        yield b"partial"
        raise httpx.ReadError("body lost after headers")


resp = httpx.Response(200, content=BrokenStream())
resp.read()  # → httpx.ReadError
```
`Response.stream` 必须是 `SyncByteStream`（不能是裸生成器，否则 `assert isinstance(...)` 失败）。

## R-03 语义区分：新增 FaultKind 而非复用 PARTIAL_SUCCESS

**决策**：新增 `FaultKind.STREAM_BODY_LOSS`，不复用 `PARTIAL_SUCCESS`。

**依据**：
- `PARTIAL_SUCCESS` 语义是「主操作已提交，但后续步骤失败」，在 `handle_request` 里**直接抛**
  `ReadError`（整个请求失败）。
- `STREAM_BODY_LOSS` 语义是「响应头到达（副作用已提交），但响应体读取丢失」，表现为**返回
  响应头正常、body 读取时才失败**的 Response。
- 两者故障细粒度不同，复用会混淆语义（宪法第 VIII 条「失败可解释」要求报告能区分故障点）。

## R-04 范围：只做 httpx，requests 列为 Out of Scope

**决策**：009 只覆盖 httpx（同步 + 异步 transport）；requests 的流式 body 丢失不做。

**依据**：
- httpx 是 003 的主适配器，流式机制干净（`SyncByteStream`/`AsyncByteStream`）。
- requests 适配器（006）刚加入、使用面较窄，且其 `Response.raw` 惰性读取机制
  （`stream(decode_content=...)`）接口细节更复杂。
- 宪法第 VII 条 YAGNI：先覆盖最主流的 httpx，requests 流式按需再补。

## R-05 检测价值：复用 NoDuplicateEffects，不新增不变量

**决策**：流式 body 丢失后的重试 → 重复副作用，复用 `NoDuplicateEffects` 检测，不新增不变量。

**依据**：流式 body 丢失的本质是「已提交 + 客户端失败 + 重试」，与 `TIMEOUT_AFTER_COMMIT`
的检测结论一致（committed 两次 → 重复）。净增量是**故障注入的细粒度**，不是检测能力。
