# Research: AgentReplayGuard MVP 技术决策

**Feature**: `001-effect-safety-testing`
**Date**: 2026-11-12
**Status**: 完成，所有 Technical Context 未知项已解决

本文件记录影响架构的关键决策、依据与替代方案。标注「已核实」的结论来自官方文档或
PyPI；标注「推断」的结论需在实现阶段用测试验证。

## R1. 副作用拦截方式

**Decision**: 采用显式 `EffectGuard` 包装用户工具函数（装饰器或 `guard.call`），不修改
LangGraph 内部，不 monkeypatch HTTP 客户端。

**Rationale**:
- 业务键（如退款单号）只有用户知道，显式包装是唯一能可靠获取业务键的方式。
- 不依赖 LangGraph 内部 API，框架升级时适配层只需处理驱动逻辑。
- 失败可解释：guard 能精确记录 attempt、参数哈希、提交状态与故障类型。
- 核心模块可完全脱离 LangGraph 单测。

**Alternatives considered**:
- **Monkeypatch requests/httpx**：只能看到 HTTP 调用，无法知道业务键；对 SDK、数据库、
  消息队列覆盖不全；极易随库版本失效。
- **LangGraph callback / ToolNode 拦截**：依赖框架内部执行细节；工具之外的副作用无法
  捕获；跨版本脆弱。
- **录制回放流量**：会屏蔽真实副作用语义，与「检测重复提交」目标相反（AgentTape 类工具
  的路线）。

**Consequence**: 用户需要在构造图时用 `@guard.effect(...)` 包裹副作用函数，属于极小且
显式的改动；这也是 MVP 的已知使用门槛（见产品定位 H1）。

## R2. 故障模型与「部分成功」

**Decision**: 故障由 `FaultPlan` 中的有序 `FaultRule` 决定，规则匹配
`effect_type / business_key / attempt / call_index`，按顺序首个匹配生效。`FaultKind` 包含
五类：`TIMEOUT_BEFORE_COMMIT`、`TIMEOUT_AFTER_COMMIT`、`CONNECTION_RESET`、
`SERVER_ERROR`、`PARTIAL_SUCCESS`。

- 提交前故障：不调用底层函数，直接抛出对应异常，记录 `NOT_COMMITTED`。
- 提交后故障（`TIMEOUT_AFTER_COMMIT`、`PARTIAL_SUCCESS`）：先调用底层函数并记录
  `COMMITTED`，再向调用方抛出异常，模拟「服务端已提交、客户端未收到确认」。
- `PARTIAL_SUCCESS` 用于多步业务操作：推荐把每个子操作分别用 guard 包裹（如先退款、
  再发通知），对后一个子操作注入故障；此时账本自然呈现「退款成功、通知失败」。

**Rationale**:
- 规则化故障比随机故障更容易复现，且能在报告中说明「为什么这一次失败」。
- 先提交再抛异常是 lost-ack 的核心语义，必须在 guard 层显式表达，不能靠 mock 的调用
  次数推断。
- 部分成功本质上是多 effect 组合，不需要为单次调用引入「部分提交」的魔法状态。

**Alternatives considered**:
- 纯概率故障：不可复现，违背原则 II。
- 在模拟服务内部注入故障：会让「客户端视角」和「服务端视角」混在一起，报告无法区分
  「没提交」与「提交了但客户端不知道」。
- 为 partial success 设计复合 effect 对象：MVP 过度设计。

**Consequence**: `TIMEOUT_AFTER_COMMIT` 与 `PARTIAL_SUCCESS` 都产生「服务端已提交 +
客户端异常」的记录；区别在异常类型与业务语义，报告中均显示 `commit_state=COMMITTED` 且
`client_error` 非空。

## R3. LangGraph 重试语义（关键发现）

**Decision**: 示例与文档必须显式配置 `RetryPolicy(retry_on=(TimeoutError, ConnectionError,
ServiceError), initial_interval=0, jitter=False)`；不依赖默认 `retry_on`。

**Rationale（已核实）**:
- LangGraph 官方 fault-tolerance 文档说明：默认 `default_retry_on` 对**大多数异常重试，
  但排除** `OSError`（以及 ValueError、TypeError、RuntimeError 等）。
- Python 中 `TimeoutError` 与 `ConnectionError` 都是 `OSError` 的子类，因此**默认策略不会
  重试超时/连接重置**；若不显式配置，lost-ack 场景根本不会触发重试，工具会给出错误的
  「安全」结论。
- 默认 `initial_interval=0.5`、`jitter=True` 会让测试变慢且引入时间抖动；示例设置
  `initial_interval=0`、`jitter=False` 以满足 <5 秒与确定性要求。

**Alternatives considered**:
- 依赖默认重试：会导致核心示例失效，已否决。
- 用自定义节点循环模拟重试：绕过 LangGraph 真实重试路径，测试价值降低。

**Consequence**: 适配层文档与 Quickstart 必须显著提示 `retry_on`；集成测试需覆盖「默认
策略不重试」与「显式策略重试」两种行为，防止未来 LangGraph 改变默认值。

## R4. LangGraph 版本与公共 API

**Decision**: MVP 支持 `langgraph>=1.2,<2.0`，以 1.2.x 为测试基线；只使用公共 API：
`StateGraph`、`add_node(retry_policy=...)`、`compile(checkpointer=InMemorySaver())`、
`invoke`、`get_state`、`Command(resume=...)`、`interrupt`。

**Rationale（已核实）**:
- PyPI 最新版本 1.2.20（2026-11-05），要求 Python >=3.10。
- 官方文档确认 `RetryPolicy` 通过 `add_node(retry_policy=...)` 配置；`Command(resume=...)`
  恢复 interrupt；`InMemorySaver` 位于 `langgraph.checkpoint.memory`。
- 1.2 起提供 `Runtime.execution_info`（含 `node_attempt`、`checkpoint_id`），但 MVP 不依赖
  它，避免把适配器绑死在新增 API 上。
- 限定 `<2.0` 避免上游破坏性变更；1.0/1.1 不纳入测试矩阵，减少组合数。

**Alternatives considered**:
- 支持 1.0+：看似更宽容，但需要额外测试矩阵，且 1.2 已是当前稳定线。
- 固定精确版本：会阻止用户升级，不适合库。
- 使用 `langgraph` 的 callback/内部 runtime：脆弱，已否决。

## R5. Checkpoint 归属粒度

**Decision**: 以「运行片段（RunSegment）」为归属单位。适配器在每次 `invoke` / resume 前
读取 `graph.get_state(config)` 的 checkpoint，记录 `checkpoint_before`；运行结束后记录
`checkpoint_after`。Effect 记录携带 `run_id`、`thread_id` 与该片段起始 checkpoint。

**Rationale**:
- 无需包裹用户节点或依赖 `Runtime` 注入，保持适配器薄且使用公共 API。
- 一次 resume 就是一个片段，足以回答「这次恢复是否重复执行了 effect」。
- 单节点内多次 effect 的 checkpoint 归属差异在 MVP 中不关键；报告仍能按 run/thread/
  checkpoint 定位。

**Alternatives considered**:
- 包裹每个节点读取 `Runtime.execution_info.checkpoint_id`：更精确，但要求用户改节点签名
 或由适配器重写节点，侵入性强。
- 只记录 thread_id：无法区分多次 resume，报告定位能力不足。

**Consequence**: 文档需说明「checkpoint 为片段级归属，不是每个 effect 的精确 checkpoint」；
若用户需要更细粒度，属于 P2 扩展。

## R6. 确定性设计

**Decision**:
- 使用单调递增的 `LogicalClock`（整数 tick），记录不含 wall clock。
- 概率规则使用 `random.Random(seed)`；默认概率 1.0，不消耗随机数。
- ID 由场景内序号生成（`eff-000001`、`run-0001`、`thread-...`），不使用 UUID。
- 参数哈希：对绑定参数做规范化 JSON（`sort_keys=True`、紧凑分隔符、`ensure_ascii=False`）
  后取 SHA-256；不可序列化时抛出明确错误。
- 默认 seed=0；报告中始终输出 seed。

**Rationale**: 原则 II 要求同场景同 seed 结果完全一致；任何 wall clock、UUID 或字典序
不稳定都会破坏回归对比。

**Alternatives considered**: 使用真实时间戳便于观察（但不可复现）；使用 `repr` 做哈希
（跨 Python 版本不稳定）。

## R7. 公开 API 与 pytest 集成

**Decision**: 公开面保持为：
- `Scenario`：场景配置与生命周期；
- `EffectGuard`：`guard.effect(...)` 装饰器与 `guard.call(...)` 直接调用；
- `EffectStore` / `EffectView`：只读查询；
- 不变量：`NoDuplicateEffects`、`MaxEffectCount`、`CustomInvariant`；
- `ScenarioReport`：`ok`、`violations`、`format()`、`assert_clean()`；
- `LangGraphAdapter`：`invoke`、`resume`、`resume_interrupt`、`state`；
- pytest 插件：`replayguard` fixture，返回场景工厂。

`EffectSafetyError` 继承 `AssertionError`，使 pytest 原生展示失败信息。

**Rationale**: 符合原则 V 的「一个入口 + 一个场景对象 + 一组查询/断言接口」；fixture
通过 `pytest11` entry point 注册，用户无需在 conftest 中手动加载。

**Alternatives considered**:
- 只提供 CLI：与 pytest 工作流脱节。
- 自动发现测试并注入故障：魔法过强，难以控制业务键。
- 暴露可变 Store 给用户：容易被误写，破坏证据链。

## R8. 模拟退款服务与幂等键

**Decision**: `SimulatedRefundService` 使用内存账本：
- `refund(refund_id, amount, idempotency_key=None)`；
- 有幂等键：相同键 + 相同参数返回已有结果，不新增账本记录；相同键 + 不同参数抛
  `IdempotencyConflict`；
- 无幂等键：每次调用都新增一条退款；
- 账本可按 `refund_id`、幂等键查询。

**Rationale**: 精确覆盖 US1/US2 的两种结论；冲突语义与真实支付服务一致，能暴露「每次
重试生成不同键」的错误实现。

**Alternatives considered**: 只按 refund_id 去重（会掩盖缺少幂等键的问题）；真实 HTTP
模拟（引入网络与依赖，违背原则 III）。

## R9. 不支持的图形态

**Decision**: MVP 明确只保证串行图。适配器在初始化时：
- 拒绝 async 调用方式（只提供同步 `invoke`）；
- 通过 `graph.get_graph()` 做保守检查：若同一节点存在多条无条件出边，抛出
  `UnsupportedGraphError`；
- 条件边导致的静态多出边可能误报，文档说明可通过 `strict=False` 跳过检查（默认
  `strict=True`，保护用户不产生不可信结论）。

**Rationale（推断，需实现验证）**: `get_graph()` 是公开 API，但静态图无法完全区分条件
分支与并行分支；保守失败比给出错误结论更符合工具定位。

**Alternatives considered**: 运行期检测并发 superstep（需要 stream 事件解析，复杂且易变）；
完全不检测（用户可能在并行图上得到错误结论）。MVP 选择保守检查 + 文档声明。

## R10. 工程与兼容性

**Decision**: `src/` 布局；构建后端 hatchling；ruff 负责 lint/format；mypy 检查公开模块；
Python 3.10–3.13 测试矩阵；核心覆盖率 ≥90%；CI 包含断网任务。

**Rationale**: 与原则 IV、V 和「小依赖」一致；hatchling 对纯 Python 包配置最少；ruff
单一工具覆盖 lint 与格式，降低维护成本。

**Alternatives considered**: setuptools（配置更繁琐）、poetry（额外生态依赖）、tox（MVP
阶段 GitHub Actions 矩阵足够）。

## R11. 原始参数与隐私

**Decision**: Effect Store 只保存参数哈希与幂等键哈希，不保存参数原文；业务键原文保留
（用于报告定位）。提供 `EffectRecord.params_hash`，不提供反查。

**Rationale**: 原则 III 要求默认不持久化业务参数原文；哈希足以判断「同键不同参数」。

**Alternatives considered**: 保存原文便于调试，但可能泄露金额、账号等敏感信息；如需调试
可在 P2 增加显式 opt-in。

## R12. 幂等键与服务端去重的判定口径

**Decision**: Effect Store 保留每条 `COMMITTED` 尝试，但 `committed_count` 与内置不变量按
「业务提交」去重：
- 有幂等键：同一 `(effect_type, business_key, idempotency_key_hash)` 只计 1 次；
- 无幂等键：每条 `COMMITTED` 计 1 次；
- 同一提交身份出现不同 `params_hash`：仍报 `parameter_mismatch` 违规。

**Rationale**:
- 若按原始记录计数，正确的幂等实现会因为「服务被调用两次」被误判为重复；这与 US2 直接
  冲突。
- 业务上关心的是「账本里有几笔」，不是「客户端调用了几次」；去重口径与模拟账本一致。
- 保留原始记录使报告仍能展示 attempt 1/2 的完整时间线。

**Assumption（需在文档中声明）**: 该口径假设外部服务确实遵守幂等键。MVP 的内置模拟服务
满足此假设；接入真实服务时，用户必须确认供应商的幂等语义，否则结论不可信。

**Alternatives considered**:
- 按原始 committed 记录计数：会把正确的幂等实现判为失败。
- 要求用户手写 `distinct_commits` 查询：增加使用门槛，且内置不变量会给出错误结论。

## 待验证项（实现阶段）

1. `graph.get_graph()` 对条件边/并行边的实际表示，校准 R9 的误报率。
2. `StateSnapshot.config` 中 checkpoint_id 的具体格式与缺失场景（首次运行前）。
3. `InMemorySaver` 在多次 invoke/resume 下的状态隔离行为。
4. LangGraph 1.2.x 各小版本对 `RetryPolicy` 参数的兼容性（至少 1.2.20 与一个较早 1.2.x）。
5. 默认 `retry_on` 的排除列表是否在 1.2.x 后续版本变化（用集成测试锁定）。

## Sources

- [LangGraph Fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance)
- [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph Use time travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)
- [LangGraph Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers)
- [langgraph 1.2.7 on PyPI](https://pypi.org/project/langgraph/1.2.7/)
- [langgraph 1.1.9 on PyPI](https://pypi.org/project/langgraph/1.1.9/)
