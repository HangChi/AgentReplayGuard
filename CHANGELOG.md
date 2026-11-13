# Changelog

本项目的所有重要变更都记录在此文件中。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

暂无。

## [0.12.0] - 2026-11-14

### Added

- 新增订单、邮件、库存三类模拟服务模板（`services/order.py`、`services/email.py`、
  `services/inventory.py`），复用退款服务的「内存账本 + 幂等键」范式，供用户仿照接入
  自己的外部服务模拟。
- 新增 `examples/more_services/test_order_lost_ack.py`，演示「模拟服务 + guard 装饰 +
  lost-ack 故障注入 + `NoDuplicateEffects`」的完整闭环。

### Changed

- 抽取共享异常 `IdempotencyConflict` 到 `services/_common.py`，退款服务改为从该模块导入
  （`services.refund.IdempotencyConflict` 仍可导入，未破坏既有用法）。

## [0.11.0] - 2026-11-14

### Added

- `ScenarioReport.to_junit_xml()`：把副作用安全检测结论导出为 JUnit XML，便于 CI 平台
  直接展示。scenario 映射为 testsuite，违规映射为 failure testcase，无违规映射为通过
  testcase。`time` 固定为 `0.0` 以保持确定性。仅使用标准库 `xml.etree`。

## [0.10.0] - 2026-11-13

### Added

- `LangGraphAdapter.stream()`：同步 stream 入口，无需 `ainvoke` 即可在同步生成器上做
  effect 归属与故障注入；`finally` 保证正常、异常、提前 `break` 三条退出路径都收尾。

### Out of Scope

- 同步 `stream_events`（LangGraph v2 仅提供异步版本，v3 仍为实验性）。

## [0.9.0] - 2026-11-13

### Added

- 新增故障类型 `FaultKind.STREAM_BODY_LOSS`：服务端已提交但流式响应体读取失败
  （提交后不抛异常，读取时抛 `ReadError`），用于复现流式场景下的 lost-ack。
- httpx 传输层支持把响应 body 包装为会失败的字节流。

### Fixed

- 修复 `STREAM_BODY_LOSS` 被记录两次的问题。

### Out of Scope

- requests 客户端的流式 body 丢失语义。

## [0.8.0] - 2026-11-13

### Added

- `ScenarioReport.to_dict()` / `to_json()`：报告结构化导出，Enum 转 value、
  dataclass 转 dict，输出确定性。用于 CI 存档、审计与跨工具消费。纯转换，无 I/O、无依赖。

## [0.7.0] - 2026-11-13

### Added

- 多框架工具接入：验证「工具函数是纯 Python callable，`guard.effect` 装饰即可」，
  补充 OpenAI Agents SDK scripted 示例，以及 CrewAI / AutoGen 接入文档。

### Fixed

- `guard.effect` 的配置参数（`key` / `params` / `idempotency_key`）与被装饰函数实参同名
  且以关键字传参时，不再抛 `TypeError: got multiple values for keyword argument`。
  配置参数改为位置参数内部传递，公开 API 签名不变。

## [0.6.0] - 2026-11-13

### Added

- requests 客户端适配器：包裹 requests 的 adapter，业务代码零改动地记账并注入 lost-ack。

## [0.5.0] - 2026-11-13

### Added

- `LangGraphAdapter.astream()` / `astream_events()`：流式接口的 effect 归属与故障注入。
  修复「绕过适配器直接 `graph.astream()` 时 effect 已记账但 `run_id` / `branch_id` 为空」
  的无主记录问题。

## [0.4.0] - 2026-11-13

### Added

- 并行 fan-out 图支持：`EffectRecord.branch_id` 记录产生 effect 的节点名，按图边注册顺序
  确定性分配分支归属。
- 新增不变量 `ConcurrentCommitDetected`：以 `started_tick` / `ended_tick` 区间重叠判定
  并发提交。
- `strict_graph=True` 语义反转：现在表示「支持 fan-out」，`False` 仅告警。

### Changed

- 明确确定性承诺范围：branch 归属与检测结论确定；并行分支的 effect 追加顺序不确定
  （同步 fan-out 是线程池真并发）。

## [0.3.0] - 2026-11-13

### Added

- HTTP 传输层故障注入：包裹 httpx 同步/异步 transport，业务代码零改动地记账并注入
  lost-ack。

## [0.2.0] - 2026-11-13

### Added

- 异步副作用安全测试：异步工具、`ainvoke` 异步图执行与异步适配层支持。

## [0.1.0] - 2026-11-12

### Added

- MVP 首个版本：面向 LangGraph + pytest 的副作用安全测试。
- `Scenario` 场景声明与 pytest 集成。
- Effect Store：记录 effect 类型、业务键、参数哈希、尝试序号、提交状态、
  run / thread / checkpoint。
- Fault Injector：提交前超时、提交后响应丢失（lost-ack）、连接重置、500、部分成功五类
  故障，由固定 seed 驱动。
- `SimulatedRefundService`：内存退款账本 + 幂等键开关。
- Invariant Checker：`NoDuplicateEffects`、`MaxEffectCount`、自定义 predicate。
- LangGraph Adapter：驱动 RetryPolicy、Checkpoint 恢复与 Interrupt 重放。
- 退款完整示例与 Quickstart 文档。

[Unreleased]: https://github.com/HangChi/AgentReplayGuard/compare/v0.12.0...HEAD
[0.12.0]: https://github.com/HangChi/AgentReplayGuard/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/HangChi/AgentReplayGuard/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/HangChi/AgentReplayGuard/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/HangChi/AgentReplayGuard/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/HangChi/AgentReplayGuard/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/HangChi/AgentReplayGuard/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/HangChi/AgentReplayGuard/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/HangChi/AgentReplayGuard/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/HangChi/AgentReplayGuard/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/HangChi/AgentReplayGuard/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/HangChi/AgentReplayGuard/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/HangChi/AgentReplayGuard/releases/tag/v0.1.0
