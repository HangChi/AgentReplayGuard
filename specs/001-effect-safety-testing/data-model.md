# Data Model: AgentReplayGuard MVP

**Feature**: `001-effect-safety-testing`
**Date**: 2026-11-12
**Note**: 字段为设计约定，不是最终 Python 签名；公开签名以 `contracts/public-api.md` 为准。

## 实体总览

```text
Scenario 1 ─── 1 EffectStore 1 ─── N EffectRecord
    │ 1
    ├──── 1 FaultInjector 1 ─── N FaultRule（来自 FaultPlan）
    ├──── N Invariant
    ├──── N RunSegment 1 ─── N EffectRecord（按 run_id 归属）
    └──── 1 ScenarioReport（finish 后生成）

SimulatedRefundService 1 ─── N Refund（内存账本）
```

## 1. Scenario（场景）

一次可复现实验的根对象，持有运行期状态。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| name | str | 非空、≤80 字符 | 报告与失败信息中的场景名 |
| seed | int | 默认 0 | 概率故障与所有随机选择的种子 |
| faults | FaultPlan | 默认空计划 | 故障规则集合 |
| invariants | tuple[Invariant, ...] | 名称唯一 | 场景结束时按顺序执行 |
| clock | LogicalClock | 内部创建 | 单调 tick，从 0 开始 |
| effects | EffectStore | 内部创建 | 本场景隔离 |
| run_segments | tuple[RunSegment, ...] | 只读 | 每次 invoke/resume 一条 |
| state | ScenarioState | CREATED / RUNNING / FINISHED | 生命周期 |

**规则**:
- 一个 Scenario 实例只能属于一次测试；`finish()` 后 guard 拒绝新的 effect 调用。
- 配置在进入 RUNNING 后不可变；可变配置通过新建 Scenario 实现。
- 默认不传 `faults` 时，仍记录 effect，但不注入故障。

## 2. EffectRecord（副作用记录）

guard 对一次副作用尝试的完整证据。只追加，不修改已终结记录。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| effect_id | str | `eff-000001`，场景内唯一 | 逻辑 ID |
| sequence | int | 从 1 递增 | 记录顺序，报告排序依据 |
| effect_type | str | 非空 | 如 `refund`、`notify` |
| business_key | str | 非空 | 业务幂等身份，如退款单号 |
| params_hash | str | 64 位小写十六进制 | 规范化参数 SHA-256 |
| idempotency_key_hash | str \| None | 同上或 None | 幂等键哈希，不存原文 |
| attempt | int | ≥1 | 同一 `(effect_type, business_key)` 的第几次尝试 |
| status | EffectStatus | 见状态机 | 服务端提交状态 |
| fault | FaultKind \| None | 枚举 | 本次注入的故障 |
| error_type | str \| None | 异常类名 | 客户端观察到的错误 |
| error_message | str \| None | ≤500 字符 | 截断后的错误信息 |
| run_id | str \| None | `run-0001` | 所属运行片段 |
| thread_id | str \| None | 用户或适配器提供 | LangGraph thread |
| checkpoint_id | str \| None | 片段起始 checkpoint | 片段级归属 |
| started_tick | int | ≥0 | 逻辑开始时间 |
| ended_tick | int \| None | ≥started_tick | 逻辑结束时间 |

**EffectStatus 状态机**:

```text
ATTEMPTED ──► COMMITTED       底层调用正常返回；即使随后注入 lost-ack 故障
ATTEMPTED ──► NOT_COMMITTED   底层调用前被故障拦截，或调用抛出且未提交
ATTEMPTED ──► UNKNOWN         调用抛出且无法判定是否已提交（显式标记）
```

- `COMMITTED` 允许同时存在 `error_type`：表示服务端已提交、客户端收到错误（lost-ack /
  partial success）。报告必须同时展示两者。
- `attempt` 在场景生命周期内按 `(effect_type, business_key)` 累计，跨 run 片段不重置；
  这与 LangGraph 的 `node_attempt` 不同，后者是节点级尝试，不对外暴露。
- 参数不可 JSON 序列化时，guard 抛出 `ScenarioConfigError`，不产生半条记录。
- **业务提交去重口径**：`EffectStore.committed_count` 与内置不变量按「业务提交」计数——
  同一 `(effect_type, business_key)` 下，有幂等键时相同 `idempotency_key_hash` 的多条
  `COMMITTED` 记录只计 1 次；无幂等键时每条计 1 次。该口径假设模拟服务遵守幂等键语义
  （R8/R12），原始尝试仍完整保留在 `records` 中。

## 3. FaultRule / FaultPlan（故障规则）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| kind | FaultKind | 必填 | 五类故障之一 |
| effect_type | str \| None | 可选匹配 | None 表示任意类型 |
| business_key | str \| None | 可选匹配 | None 表示任意业务键 |
| attempt | int \| None | ≥1 | 精确匹配第几次尝试 |
| call_index | int \| None | ≥1 | 场景内第几次 guarded 调用 |
| times | int | ≥1，默认 1 | 命中次数上限 |
| probability | float | 0.0–1.0，默认 1.0 | 命中后是否生效；使用 seed |

**规则顺序**：按声明顺序匹配，首个满足条件的规则生效；`times` 用尽后继续尝试后续规则。
**校验**：至少声明一个选择器（effect_type / business_key / attempt / call_index），避免
误伤所有 effect；`probability < 1.0` 时使用 `Scenario.seed`（默认 0）做确定性判定。

**FaultKind 语义**:

| Kind | 提交 | 客户端异常 | 典型场景 |
|------|------|------------|----------|
| TIMEOUT_BEFORE_COMMIT | 否 | `TimeoutError` | 请求未到达服务 |
| TIMEOUT_AFTER_COMMIT | 是 | `TimeoutError` | 提交成功但响应丢失 |
| CONNECTION_RESET | 否 | `ConnectionResetError` | 连接被重置 |
| SERVER_ERROR | 否 | `ServiceError(status=500)` | 服务端 5xx |
| PARTIAL_SUCCESS | 是 | `PartialSuccessError` | 主操作成功、后续步骤失败 |

## 4. RunSegment（运行片段）

适配器每次 `invoke` / `resume` / `resume_interrupt` 产生一条。

| 字段 | 类型 | 说明 |
|------|------|------|
| run_id | str | 场景内唯一，`run-0001` |
| thread_id | str | LangGraph thread |
| input_kind | START / RESUME / INTERRUPT_RESUME | 片段类型 |
| checkpoint_before | str \| None | 调用前 `get_state` 的 checkpoint |
| checkpoint_after | str \| None | 调用后 `get_state` 的 checkpoint |
| started_tick / ended_tick | int | 逻辑时间 |
| interrupted | bool | 本次是否停在 interrupt |
| error_type / error_message | str \| None | 图执行失败信息（若有） |

**状态机**: `STARTED → COMPLETED | INTERRUPTED | FAILED`；终止态不可回退。

## 5. Invariant / Violation（不变量与违规）

**Invariant 协议**（内部）: `name: str` + `check(view: EffectView) -> list[Violation]`。

| 内置不变量 | 参数 | 判定 |
|------------|------|------|
| NoDuplicateEffects | effect_type: str \| None = None | 按 `(effect_type, business_key)` 分组，按业务提交去重后 >1 即违规；同一提交身份出现不同 `params_hash` 时附加 `parameter_mismatch` |
| MaxEffectCount | effect_type: str, max_count: int ≥0 | 去重后业务提交数 > max_count 即违规 |
| CustomInvariant | name: str, predicate: Callable[[EffectView], bool] | predicate 返回 False 或抛异常即违规 |

**Violation 字段**: `invariant_name`、`message`、`expected`、`actual`、`effect_ids`。
报告按不变量声明顺序、再按 `effect_ids` 排序，保证输出确定。

## 6. SimulatedRefundService / Refund（退款模拟）

| Refund 字段 | 类型 | 说明 |
|-------------|------|------|
| refund_id | str | 退款单号（业务键） |
| amount_cents | int | 金额，避免浮点误差 |
| idempotency_key | str \| None | 幂等键原文，仅存于模拟账本 |
| committed_tick | int | 逻辑提交时间 |
| ledger_sequence | int | 账本顺序 |

**行为规则**:
- 无幂等键：每次调用新增一条 Refund。
- 有幂等键且键已存在、参数相同：返回既有 Refund，不新增。
- 有幂等键但参数不同：抛 `IdempotencyConflict`，不新增。
- 查询：`by_refund_id(id)`、`by_idempotency_key(key)`、`count()`。

## 7. ScenarioReport（运行报告）

| 字段 | 类型 | 说明 |
|------|------|------|
| scenario_name | str | 场景名 |
| seed | int | 复现种子 |
| effects | tuple[EffectRecord, ...] | 按 sequence 排序 |
| run_segments | tuple[RunSegment, ...] | 按 run_id 排序 |
| violations | tuple[Violation, ...] | 按不变量顺序 |
| warnings | tuple[str, ...] | 未声明不变量、strict_graph=False 等提示 |
| ok | bool | `violations` 为空 |

**方法**: `format() -> str`（确定性文本）、`assert_clean() -> None`（有违规则抛
`EffectSafetyError`，继承 `AssertionError`）。

## 8. 生命周期与隔离

```text
CREATED ──(首次 invoke/guard.call)──► RUNNING ──(finish)──► FINISHED
   │                                      │
   └──────────── finish 允许提前结束 ──────┘
```

- 每个 Scenario 拥有独立 Store、Clock、Injector、attempt 计数与账本；测试之间不共享。
- `finish()` 执行全部不变量并冻结场景；重复调用返回同一份报告。
- 场景结束后继续调用 guard 或 adapter 抛 `ScenarioStateError`。
- 报告不包含 wall clock、绝对路径、内存地址，保证跨运行可比较。
