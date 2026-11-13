# Research: 异步副作用安全测试

**Date**: 2026-11-13 | **Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

## D1. 异步工具的识别方式

- **Decision**: 在 `EffectGuard.effect` 装饰时使用 `inspect.iscoroutinefunction` 判断，
  异步函数返回异步 wrapper，同步函数保持现有同步 wrapper；公开声明方式不变。
- **Rationale**: 用户无需为异步工具学习第二套声明；同步 API 与类型签名保持不变；
  避免在调用时猜测而引入歧义。
- **Alternatives considered**:
  - 新增独立 `async_effect` 装饰器：多一套 API，用户需记住选择，违背最小接口面。
  - 运行时判断返回值是否 awaitable：会把「同步函数返回协程」的误用掩盖为正常路径。

## D2. 异步调用入口

- **Decision**: 新增 `EffectGuard.acall(...)`（async），保留 `call(...)`（sync）。
  `call` 在入口处检测到协程函数立即抛 `ScenarioConfigError`，且在解析参数与写入账本之前
  完成检测。
- **Rationale**: 关闭「协程对象被当作成功结果记为 committed」的缺陷；错误发生在任何状态
  变更之前，保证账本无污染。
- **Alternatives considered**:
  - 让 `call` 自动运行协程（`asyncio.run`）：在已有事件循环中会失败，且同步上下文可能
    本就不允许阻塞，语义不清晰。
  - 仅文档警告：无法阻止测试假通过，风险不可接受。

## D3. 同步与异步的记账一致性

- **Decision**: 抽出一个私有的「尝试准备 + 记录」辅助结构，同步与异步路径共享参数绑定、
  业务键/参数哈希解析、attempt 分配、故障指令获取、run 上下文读取与记录写入；两条路径
  仅在「执行函数」这一步不同（直接调用 vs await）。
- **Rationale**: 记账规则（尤其 attempt 序号、去重口径、提交前后故障语义）是产品核心，
  复制两份实现会随迭代漂移；共享内部辅助结构不扩大公开 API。
- **Alternatives considered**:
  - 完全复制两套实现：初期简单，但任何记账规则调整都要改两处，违背宪法 IV/VIII 的风险
    控制目标。
  - 用线程池把异步转同步：引入执行器与线程语义，破坏确定性。

## D4. 取消语义

- **Decision**: 异步执行中捕获 `asyncio.CancelledError`，记录 `EffectStatus.UNKNOWN`
  （结果未知），随后原样向上传播；不记录 `COMMITTED`，也不吞掉取消。
- **Rationale**: 取消发生时服务端是否已提交无法确定，`UNKNOWN` 是既有枚举中唯一诚实状态；
  Python 3.8+ 中 `CancelledError` 继承 `BaseException`，不会被现有 `except Exception` 捕获，
  必须显式处理。
- **Alternatives considered**:
  - 记为 `NOT_COMMITTED`：会掩盖可能已提交的副作用，导致漏报重复。
  - 不记录：账本缺少该次尝试，attempt 序列出现空洞，报告难以解释。

## D5. 异步图驱动

- **Decision**: 适配器新增 `ainvoke`、`aresume`、`aresume_interrupt`，内部共用 run 片段
  构建逻辑，仅把 `graph.invoke` 替换为 `await graph.ainvoke`。异步入口首次调用时校验
  `ainvoke` 是否存在，缺失则抛 `UnsupportedGraphError`。
- **Rationale**: 行为与同步入口保持镜像；校验延迟到异步入口，避免要求同步用户提供
  `ainvoke`（虽然 LangGraph 编译图两者都有，但假 graph/stub 测试不应被强制）。
- **Alternatives considered**:
  - 在构造时同时要求 `invoke` 与 `ainvoke`：会破坏现有假 graph 单元测试与自定义实现。
  - 提供统一 `run(async=...)` 参数：接口更复杂，且同步调用点无法 await。

## D6. 测试驱动方式

- **Decision**: 所有异步测试在同步 pytest 用例内使用 `asyncio.run(...)` 驱动；不引入
  pytest-asyncio 或 anyio 依赖。
- **Rationale**: 保持「pytest 是唯一入口、核心包零依赖」的约束；避免为测试增加插件兼容
  矩阵；`asyncio.run` 在 3.10+ 行为稳定。
- **Alternatives considered**:
  - 增加 pytest-asyncio dev 依赖：会给用户示例传达「必须安装插件」的错误信号。
  - 自建事件循环 fixture：等价于重复 `asyncio.run`，无收益。

## D7. 不在本次范围的能力

- **Decision**: 不实现 `astream`/`astream_events`、并发任务、并行图、后台任务与跨进程。
- **Rationale**: 流式接口的故障注入点与断言语义需要单独设计；并发会引入调度非确定性，
  与「同一 seed 完全一致」冲突。按宪法 VII 克制范围。
- **Alternatives considered**: 先做 `astream` 的最小版本；被拒绝，因为缺少真实需求证据，
  且会把报告结构从「按 run 汇总」推向「按事件流汇总」。

## D8. 版本与兼容性

- **Decision**: 功能合并后将包版本从 `0.1.0` 提升到 `0.2.0`；同步 API 不动，异步为新增。
- **Rationale**: 新增公开方法属于 SemVer minor；尚未发布过 0.1.0，但保留清晰的功能边界。
- **Alternatives considered**: 保持 0.1.0 直到首次发布；可行，但会让发布说明难以界定特性
  范围，故选择 minor 提升。
