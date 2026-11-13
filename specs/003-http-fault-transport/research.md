# Research: HTTP 故障注入传输层

**Date**: 2026-11-13 | **Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## 决策 1：以传输层作为接缝

- **Decision**: 适配器包裹 HTTP 客户端的 transport（`httpx.BaseTransport` /
  `httpx.AsyncBaseTransport`），不包裹 Client、不 monkeypatch、不要求业务代码改调用方式。
- **Rationale**: transport 是所有请求的必经之路，可同时覆盖 SDK、手写请求与第三方封装；
  客户端构造后代码零改动；接缝稳定且公开。
- **Alternatives considered**:
  - 包裹 Client 方法（`client.post` 等）：需要用户替换客户端对象，且会漏掉 SDK 内部调用。
  - 事件钩子（`event_hooks`）：只能观察请求/响应，无法在「提交后」撤销响应或注入异常。
  - 自定义 Auth/中间件：语义不匹配，且不同库接口不一致。

## 决策 2：可选依赖隔离

- **Decision**: 新增可选 extra `httpx = ["httpx>=0.27,<1.0"]`；适配器位于
  `agentreplayguard.adapters.httpx`，仅在用户显式导入时加载；模块内 `import httpx` 失败时
  抛出带安装提示的 `ImportError`。核心 `__init__.py` 不导入该模块。
- **Rationale**: 遵守宪法「核心包仅标准库」；未安装 httpx 的用户不受影响；错误信息可直接
  指导安装 `agentreplayguard[httpx]`。
- **Alternatives considered**:
  - 把 httpx 纳入核心依赖：违反依赖策略，增大安装面。
  - 在 `__init__.py` 中条件导出：会让 import 路径与可选依赖耦合，且改名后易误用。

## 决策 3：用分类回调把请求映射为 effect 语义

- **Decision**: 用户提供 `classify: Callable[[httpx.Request], HttpEffect | None]`。
  `HttpEffect` 含 `effect_type`、`business_key`、`params`、可选 `idempotency_key`。返回
  `None` 表示透传，不记账、不消耗故障计划。
- **Rationale**: 传输层只拿到请求，无法自行推断业务语义；回调让用户完全掌控读写区分、
  业务键来源（URL/头/JSON 体）与参与哈希的参数；显式返回 `None` 比隐式猜测安全。
- **Alternatives considered**:
  - 内置 URL 模板/JSONPath 规则 DSL：复杂度高，且难以覆盖各项目约定，违反 YAGNI。
  - 按 HTTP 方法自动推断读写：不可靠（GET 也可能有副作用，POST 既可能是查询）。

## 决策 4：复用 EffectGuard 的记账与故障注入

- **Decision**: 已分类请求统一走 `scenario.guard().call(effect_type, base.handle_request,
  request, key=..., params=..., idempotency_key=...)`；异步走 `acall`，底层函数为
  `base.handle_async_request`。
- **Rationale**: 参数哈希、幂等键哈希、attempt 分配、故障计划消耗、run/thread/checkpoint
  归属、取消与异常状态全部复用既有语义，天然与函数级 guard 一致，避免第二套账本。
- **Alternatives considered**:
  - 适配器内直接写 EffectStore：重复实现哈希与状态机，易漂移，且破坏模块边界。
  - 先自行判定故障再记账：会重复消耗故障计划或跳过 guard 的配置校验。

## 决策 5：故障阶段与异常映射

- **Decision**: 捕获 guard 抛出的异常后，读取本次调用新增的账本记录：
  - 记录存在且 `fault is not None` 时，按 `record.fault` 映射为 httpx 标准异常；
  - 否则原样传播（底层业务异常不得包装）。

  映射表：

  | FaultKind | 账本状态 | 向调用方抛出的异常 |
  |-----------|----------|--------------------|
  | `timeout_before_commit` | `not_committed` | `httpx.ConnectTimeout` |
  | `timeout_after_commit` | `committed` | `httpx.ReadTimeout` |
  | `connection_reset` | `not_committed` | `httpx.ConnectError` |
  | `server_error` | `not_committed` | `httpx.HTTPStatusError`（附 500 响应） |
  | `partial_success` | `committed` | `httpx.ReadError` |

- **Rationale**: guard 对提交前/后统一抛 `TimeoutError`，调用方无法区分；账本已由 guard 在
  抛出前写入，读取新增记录即可零成本恢复阶段信息，无需扩展 guard 公开 API。映射为客户端
  标准异常后，用户现有重试逻辑可直接生效。
- **Alternatives considered**:
  - 扩展 guard 返回故障阶段：扩大公开接口面，且函数级用户并不需要。
  - 仅映射 `TimeoutError` 为 `ReadTimeout`：无法区分提交前，重试语义错误。
  - 让 `ServiceError` 直接外泄：不是 httpx 异常，用户按客户端异常捕获会漏掉。

  **实现约束**：通过「调用前记录数量 + 调用后新增记录」定位本次记录，避免并发或历史记录
  干扰；不支持并发，因此顺序确定。

## 决策 6：提交边界与流式响应

- **Decision**: 以底层 transport 返回响应（即响应头到达）作为提交边界。流式响应体的读取
  失败语义不在本次范围；适配器不额外区分 `client.stream`，因为 httpx 不在请求对象上暴露
  流式标记。文档需注明该边界。
- **Rationale**: transport 层能观察到的「提交」就是请求已被服务端接收并返回响应头；响应体
  的后续读取发生在 transport 之外，无法可靠注入 lost-ack。
- **Alternatives considered**:
  - 在响应流包装器上注入读取故障：超出本次范围，且会引入第二个故障时机模型。
  - 拒绝所有流式请求：transport 无法识别，且会误伤正常请求。

## 决策 7：同步/异步一致性

- **Decision**: 同步与异步适配器共享同一个分类与校验函数、同一映射表与同一错误信息模板；
  仅在调用 `call` / `acall` 和 transport 方法上分叉。
- **Rationale**: 保证同一 seed、同一故障计划下记录数量、状态序列与 attempt 序号一致；
  减少重复逻辑。
- **Alternatives considered**:
  - 两份独立实现：易漂移，且测试无法做等价断言。

## 决策 8：离线测试与示例

- **Decision**: 全部测试与示例使用 `httpx.MockTransport`（同步/异步同一 handler），不建立
  真实连接；取消测试由 handler 主动抛 `asyncio.CancelledError` 触发。
- **Rationale**: 满足宪法「测试不得依赖真实网络」；MockTransport 是 httpx 官方提供的
  进程内实现，语义与真实 transport 一致。
- **Alternatives considered**:
  - 本地 HTTP 服务器：引入端口、线程与超时不确定性。
  - monkeypatch socket：脆弱且无法覆盖异步路径。

## 决策 9：版本与发布

- **Decision**: 版本从 `0.2.0` 升至 `0.3.0`（新增向后兼容特性）；`dev` extra 增加
  `httpx>=0.27,<1.0`；README 与 quickstart 增加 HTTP 用法。
- **Rationale**: 遵循 SemVer（MINOR 为向后兼容新增）；保持开发环境与测试可复现。
- **Alternatives considered**:
  - 不升版本：发布产物无法区分能力边界。MUST NOT。
