# Public API Contract: AgentReplayGuard MVP

**Feature**: `001-effect-safety-testing`
**Date**: 2026-11-12
**Status**: Implemented（v0.14.0 已发布；变更需更新本文件与契约测试）

本文件定义 MVP 的公开 Python API。所有签名以 `src/agentreplayguard/__init__.py` 的导出为准；
内部模块路径不构成兼容承诺。

## 导入面

```python
from agentreplayguard import (
    Scenario,
    EffectGuard,
    EffectStore,
    EffectView,
    EffectRecord,
    EffectStatus,
    FaultKind,
    FaultRule,
    FaultPlan,
    Invariant,
    NoDuplicateEffects,
    ConcurrentCommitDetected,
    MaxEffectCount,
    CustomInvariant,
    Violation,
    ScenarioReport,
    RunSegment,
    RunInputKind,
    GraphRun,
    EffectSafetyError,
    ScenarioConfigError,
    ScenarioStateError,
    UnsupportedGraphError,
    ServiceError,
    PartialSuccessError,
)
from agentreplayguard.services.refund import (
    SimulatedRefundService,
    Refund,
    IdempotencyConflict,
)
from agentreplayguard.adapters.langgraph import LangGraphAdapter
```

`agentreplayguard` 核心包 MUST 可在未安装 `langgraph` 时导入；只有导入
`agentreplayguard.adapters.langgraph` 时才要求 optional extra。

## Scenario

```python
class Scenario:
    def __init__(
        self,
        name: str,
        *,
        seed: int = 0,
        faults: FaultPlan | None = None,
        invariants: Sequence[Invariant] = (),
    ) -> None: ...

    @property
    def effects(self) -> EffectStore: ...

    def guard(self) -> EffectGuard: ...

    def finish(self) -> ScenarioReport: ...

    # 运行期公开接口（v0.14.0 收敛；供 LangGraphAdapter 等外部驱动方使用）
    def begin_run(self, thread_id: str, checkpoint_id: str | None) -> tuple[str, int]:
        """开启一次 run：登记 run_id/thread/checkpoint 并推进逻辑时钟。

        返回 (run_id, started_tick)，二者都用于后续构造 RunSegment。"""
        ...

    def end_run(self, segment: RunSegment) -> RunSegment:
        """收尾一次 run：补全 ended_tick、登记 segment 并清理 run 上下文。"""
        ...

    def set_branch_resolver(self, resolver: Callable[[], str | None]) -> None:
        """注入分支归属解析器（适配器层使用）。"""
        ...

    def warn(self, message: str) -> None:
        """追加一条场景级警告（进入报告 warnings）。"""
        ...
```

**契约**:
- `name` 非空；`seed` 为 int；`invariants` 名称必须唯一。
- 每个 Scenario 实例只能用于一个测试；首次调用 guard/adapter 后进入 RUNNING，配置不可变。
- `finish()` 执行不变量并返回报告；重复调用返回同一对象。FINISHED 后 guard 抛
  `ScenarioStateError`。
- 未声明不变量时，`finish()` 不失败，但报告包含 warning 条目（见 ScenarioReport）。

## EffectGuard

```python
class EffectGuard:
    def effect(
        self,
        effect_type: str,
        *,
        key: str | Callable[[Mapping[str, Any]], str],
        params: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        idempotency_key: str | Callable[[Mapping[str, Any]], str | None] | None = None,
    ) -> Callable[[F], F]: ...

    def call(
        self,
        effect_type: str,
        fn: Callable[..., T],
        *args: Any,
        key: str | Callable[[Mapping[str, Any]], str],
        params: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        idempotency_key: str | Callable[[Mapping[str, Any]], str | None] | None = None,
        **kwargs: Any,
    ) -> T: ...
```

**行为契约**:
1. 用 `inspect.signature(fn).bind(*args, **kwargs)` 绑定参数；`key` 为字符串时按参数名取值，
   为 callable 时接收绑定后的参数映射。取不到、为空或非 str 时抛 `ScenarioConfigError`。
2. `params` 默认使用全部绑定参数，但排除作为 `key` 参数与 `idempotency_key` 参数的项；
   返回映射后做规范化 JSON（排序键、紧凑分隔符、`ensure_ascii=False`）并取 SHA-256。
   不可序列化或非映射时抛 `ScenarioConfigError`。
3. `idempotency_key` 为字符串时按参数名取值，为 callable 时接收参数映射；只记录哈希。
4. 每次调用递增 `(effect_type, business_key)` 的 attempt；attempt 跨 run 片段累计。
5. 故障在调用前后按 `FaultPlan` 判定：
   - 提交前故障：记录 `NOT_COMMITTED`，抛出对应异常，不调用 `fn`。
   - 正常返回：记录 `COMMITTED`，返回结果。
   - 提交后故障：记录 `COMMITTED` 且 `error_*` 非空，再抛出异常。
   - `fn` 自身抛出：记录 `NOT_COMMITTED`（默认），重新抛出原异常。
6. guard 必须保留被装饰函数的签名与元数据（`functools.wraps`），且不吞异常。

## EffectStore / EffectView

```python
class EffectStore:
    @property
    def records(self) -> tuple[EffectRecord, ...]: ...
    def for_effect(self, effect_type: str) -> tuple[EffectRecord, ...]: ...
    def for_key(self, effect_type: str, business_key: str) -> tuple[EffectRecord, ...]: ...
    def committed_count(self, effect_type: str | None = None) -> int: ...
    def attempts(self, effect_type: str, business_key: str) -> int: ...

    # 记账公开接口（v0.14.0 收敛；由 EffectGuard 与适配器/测试使用）
    def next_attempt(self, effect_type: str, business_key: str) -> int:
        """登记一次新的尝试，返回递增后的 attempt 序号（从 1 起）。"""
        ...

    def append(self, record: EffectRecord) -> EffectRecord:
        """追加一条 effect 记录并分配 effect_id / sequence。

        入参的 ``effect_id`` 与 ``sequence`` 视为占位值（请传空串与 0），
        由账本在此统一分配，保证 identity 口径一致；返回补全后的正式记录。"""
        ...


class EffectView(Protocol):
    @property
    def records(self) -> tuple[EffectRecord, ...]: ...
    def for_effect(self, effect_type: str) -> tuple[EffectRecord, ...]: ...
    def for_key(self, effect_type: str, business_key: str) -> tuple[EffectRecord, ...]: ...
    def committed_count(self, effect_type: str | None = None) -> int: ...
```

**契约**:
- 所有查询返回按 `sequence` 升序的不可变元组。
- `committed_count(effect_type)` 统计**去重后的业务提交数**：同一业务键下，相同幂等键的
  多条 `COMMITTED` 记录只计 1 次；无幂等键时每条记录计 1 次。原始记录仍可通过
  `records` 查看。
- `next_attempt` / `append` 是账本写入入口（v0.14.0 起公开），供 `EffectGuard` 与适配器
  使用：`next_attempt` 递增 attempt 计数，`append` 统一分配 `effect_id` / `sequence` 后
  落账并返回补全记录。Store 不提供清空方法，也不允许绕过账本直接写入 `records`。
- Store 不是线程安全的；一个 Scenario 只允许单线程执行（MVP 仅串行图）。

## EffectRecord / EffectStatus

```python
class EffectStatus(str, Enum):
    ATTEMPTED = "attempted"
    COMMITTED = "committed"
    NOT_COMMITTED = "not_committed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EffectRecord:
    effect_id: str
    sequence: int
    effect_type: str
    business_key: str
    params_hash: str
    idempotency_key_hash: str | None
    attempt: int
    status: EffectStatus
    fault: FaultKind | None
    error_type: str | None
    error_message: str | None
    run_id: str | None
    thread_id: str | None
    checkpoint_id: str | None
    started_tick: int
    ended_tick: int | None
```

**契约**: 字段只读；`COMMITTED` 可与 `error_type` 同时存在（lost-ack / partial success）；
`error_message` 截断至 500 字符；不存参数原文。

## 故障模型

```python
class FaultKind(str, Enum):
    TIMEOUT_BEFORE_COMMIT = "timeout_before_commit"
    TIMEOUT_AFTER_COMMIT = "timeout_after_commit"
    CONNECTION_RESET = "connection_reset"
    SERVER_ERROR = "server_error"
    PARTIAL_SUCCESS = "partial_success"


@dataclass(frozen=True)
class FaultRule:
    kind: FaultKind
    effect_type: str | None = None
    business_key: str | None = None
    attempt: int | None = None
    call_index: int | None = None
    times: int = 1
    probability: float = 1.0


class FaultPlan:
    def __init__(self, rules: Sequence[FaultRule] = ()) -> None: ...
```

**契约**:
- 规则按顺序匹配；首个命中且未耗尽 `times` 的规则生效。
- 规则必须至少指定一个选择器（`effect_type` / `business_key` / `attempt` / `call_index`），
  否则构造时抛 `ScenarioConfigError`。
- `times >= 1`，`0.0 <= probability <= 1.0`；概率判定使用 `Scenario.seed`。
- `TIMEOUT_BEFORE_COMMIT` → `TimeoutError`；`CONNECTION_RESET` →
  `ConnectionResetError`；`SERVER_ERROR` → `ServiceError(status=500)`；
  `TIMEOUT_AFTER_COMMIT` → 提交后 `TimeoutError`；`PARTIAL_SUCCESS` → 提交后
  `PartialSuccessError`。

## 不变量

```python
class Invariant(Protocol):
    name: str

    def check(self, view: EffectView) -> list[Violation]: ...


class NoDuplicateEffects:
    def __init__(self, effect_type: str | None = None) -> None: ...


class ConcurrentCommitDetected:
    """检测同一业务键被「并发」提交（effect 区间重叠）。

    判定基于 `started_tick` / `ended_tick` 区间重叠：两条 COMMITTED 记录同
    (effect_type, business_key)，若区间相交
    （`a.started < b.ended and b.started < a.ended`）即为并发提交。
    与 `NoDuplicateEffects` 正交：前者判「并发」，后者判「重复」。
    """

    def __init__(self, effect_type: str | None = None) -> None: ...


class MaxEffectCount:
    def __init__(self, effect_type: str, max_count: int) -> None: ...


class CustomInvariant:
    def __init__(
        self,
        name: str,
        predicate: Callable[[EffectView], bool],
        *,
        message: str = "",
    ) -> None: ...


@dataclass(frozen=True)
class Violation:
    invariant_name: str
    message: str
    expected: Any
    actual: Any
    effect_ids: tuple[str, ...]
```

**契约**:
- 内置不变量只统计 `COMMITTED` 记录，并按「业务提交」去重：
  - 有幂等键：同一 `(effect_type, business_key, idempotency_key_hash)` 只计 1 次提交；
  - 无幂等键：每条 `COMMITTED` 记录计 1 次提交。
- `NoDuplicateEffects` 按 `(effect_type, business_key)` 分组，去重后提交数 >1 即违规；
  message 必须区分 `duplicate_effects`（多个不同幂等键或无幂等键）与
  `parameter_mismatch`（同一提交身份出现不同 `params_hash`），并在 `effect_ids` 中列出
  全部相关记录。
- `ConcurrentCommitDetected` 对 `COMMITTED` 记录按 `started_tick` / `ended_tick` 区间
  重叠判定「并发提交」（仅同 `(effect_type, business_key)` 之间比较）；区间不相交或
  `ended_tick is None` 的记录不判并发。与 `NoDuplicateEffects` 正交（并发 vs 重复），
  两者可同时声明。
- `MaxEffectCount` 的 `max_count >= 0`；`effect_type` 非空；计数口径同上（去重后提交数）。
- `CustomInvariant` 的 predicate 抛异常视为违规，异常信息进入 `message`。
- `Violation` 按不变量声明顺序返回；同一不变量内按 `effect_ids` 字典序。

## ScenarioReport / RunSegment / GraphRun

```python
class ScenarioReport:
    scenario_name: str
    seed: int
    effects: tuple[EffectRecord, ...]
    run_segments: tuple[RunSegment, ...]
    violations: tuple[Violation, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool: ...
    def format(self) -> str: ...
    def assert_clean(self) -> None: ...
```

**契约**:
- `ok` 为 `violations` 为空；`warnings` 不导致失败，但 `format()` 必须展示。
- `format()` 输出确定性文本，包含：场景名、seed、每条 effect 的 effect_type / business_key /
  attempt / status / fault / run_id / thread_id / checkpoint_id、违规的期望值 vs 实际值。
- `assert_clean()` 在 `ok=False` 时抛 `EffectSafetyError`（继承 `AssertionError`），
  消息等于 `format()`；pytest 可直接展示。
- 报告不含 wall clock、绝对路径、对象内存地址。

```python
class RunInputKind(str, Enum):
    START = "start"
    RESUME = "resume"
    INTERRUPT_RESUME = "interrupt_resume"


@dataclass(frozen=True)
class RunSegment:
    run_id: str
    thread_id: str
    input_kind: RunInputKind
    checkpoint_before: str | None
    checkpoint_after: str | None
    started_tick: int
    ended_tick: int
    interrupted: bool
    error_type: str | None
    error_message: str | None


@dataclass(frozen=True)
class GraphRun:
    segment: RunSegment
    output: Mapping[str, Any] | None
    interrupts: tuple[Any, ...]

    @property
    def interrupted(self) -> bool: ...
```

## LangGraphAdapter

```python
class LangGraphAdapter:
    def __init__(
        self,
        scenario: Scenario,
        graph: Any,
        *,
        thread_id: str | None = None,
        strict_graph: bool = True,
    ) -> None: ...

    @property
    def thread_id(self) -> str: ...

    def invoke(self, input: Mapping[str, Any] | None = None) -> GraphRun: ...
    def resume(self, input: Mapping[str, Any] | None = None) -> GraphRun: ...
    def resume_interrupt(self, value: Any = None) -> GraphRun: ...
    def state(self) -> Any: ...
```

**契约**:
- 构造时校验 graph 具备 `invoke`、`get_state`、`get_graph`；否则抛 `UnsupportedGraphError`。
- `invoke` 使用 `config={"configurable": {"thread_id": self.thread_id}}`；首次调用前记录
  checkpoint_before（可能为 None）。
- `resume` 等价于以 `None`/给定 input 再次 invoke，从最新 checkpoint 继续。
- `resume_interrupt(value)` 使用 `Command(resume=value)`，要求 graph 编译时带 checkpointer。
- 每次调用创建一个 RunSegment，并把 run_id / thread_id / checkpoint_before 写入 effect 记录。
- 返回值中的 `interrupts` 来自 `output["__interrupt__"]`（缺失则为空元组）。
- `strict_graph=True` 时，若 `get_graph()` 显示同一节点存在多条无条件出边，抛
  `UnsupportedGraphError`；`False` 时跳过检查并记录 warning。
- 适配器 MUST NOT 修改用户 graph、MUST NOT 包裹用户节点、MUST NOT import 私有模块。

## pytest 插件

```python
# 自动注册：pytest11 entry point "agentreplayguard"
@pytest.fixture
def replayguard() -> Callable[..., Scenario]: ...
```

**契约**: fixture 返回 `Scenario` 构造器；每个测试获得全新实例；插件不执行任何全局补丁。

## 异常

| 异常 | 基类 | 触发条件 |
|------|------|----------|
| `EffectSafetyError` | `AssertionError` | 不变量违规，`assert_clean()` |
| `ScenarioConfigError` | `ValueError` | 场景/规则/参数哈希配置非法 |
| `ScenarioStateError` | `RuntimeError` | FINISHED 后继续使用场景 |
| `UnsupportedGraphError` | `RuntimeError` | 图不具备所需 API 或检测到并行出边 |
| `ServiceError` | `Exception` | 模拟服务端 5xx，含 `status` |
| `PartialSuccessError` | `Exception` | 部分成功故障 |
| `IdempotencyConflict` | `Exception` | 同幂等键不同参数 |

## 兼容性

- Python 3.10–3.13。
- `langgraph>=1.2,<2.0`；仅使用公共 API。
- `pytest>=8` 使用插件；不安装 pytest 时核心库仍可导入（fixture 不可用）。
- Linux / macOS 为支持平台；Windows best-effort。
- 无网络、无遥测、无后台线程。
