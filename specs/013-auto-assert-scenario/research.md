# Research: 场景自动断言（消除静默漏报）

**Feature**: 013-auto-assert-scenario
**Status**: Implemented
**Date**: 2026-11-14

## R-01 问题证据：三种静默漏报形态（已实测）

**决策**：本特性由**实测复现的漏报**驱动，不是假设性需求。

**实测记录**（在本仓库用临时 pytest 文件验证，见下方「复现方式」）：

| 探针 | 用户写法 | 实际发生 | 测试结果 | 应有结果 |
|------|----------|----------|----------|----------|
| P1 | 造场景 + 触发 2 笔重复退款 + **忘记 `finish()`** | 账本确有 2 笔 COMMITTED | **passed** | 失败 |
| P2 | 造场景 + 重复退款 + `finish()` 但**不断言** | report.ok=False | **passed** | 失败 |
| P3 | 造场景 + 声明不变量 + **完全没用** | 什么都没检查 | **passed** | 失败或提示 |
| P4 | 造场景 + 重复退款 + 业务断言先失败 | 场景未收尾 | failed（但漏掉副作用结论） | 失败并带副作用结论 |

**复现方式**（P1，其余同构）：

```python
def test_forgot_finish(replayguard):
    scenario = replayguard(
        "forgot-finish",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id")
    def refund(refund_id: str) -> str:
        return refund_id

    for _ in range(2):
        try:
            refund("R-1")
        except TimeoutError:
            pass
    # 故意不调用 scenario.finish() → 测试仍 passed
```

**为何这是最高优先级缺陷**：产品的全部价值是「有重复副作用就失败」。用户忘记一行断言就
静默通过，等于工具在最关键处失效，且失效方式是「假装成功」——比报错更危险。

## R-02 项目自身数据佐证

**决策**：用仓库内统计作为「真实使用形态」的证据。

**实测统计**（`grep` 全仓 `tests/` 与 `examples/`）：

- `.finish()` 调用：**80 次**
- `.assert_clean()` 调用：**6 次**
- 34 个含 `finish()` 的文件中，**仅 1 个**（`examples/refund/test_refund_lost_ack.py`）用了
  `assert_clean()`；其余 33 个改为手写 `assert not report.ok` / `assert report.ok`。

结论：即便项目作者本人，也有 93% 的场景不做自动断言，全靠手写。这不是用户疏忽，是
**API 设计把「正确性」交给了调用方的记忆力**。

## R-03 生态标准解法：pytest fixture teardown 断言

**决策**：用 pytest fixture 的 `yield` 后置段做自动断言，而不是要求用户多写一行。

**依据（实测 + 生态惯例）**：

1. pytest 官方与社区通行做法：fixture 中 `yield` 之后的代码无论测试体通过、失败还是抛异常
   都会执行，适合放「收尾检查」。这与本场景完全吻合。
2. 实测（临时文件验证）：teardown 中 `assert` 失败时，该测试被标记为 **ERROR**（而非
   FAILED）。这是 pytest 的语义：测试体通过但收尾失败 → error。
3. 实测：若测试体**已经失败**，teardown 断言**也会**再报一次，产生「1 failed + 1 error」
   叠加噪音。**这是必须在设计中处理的约束**（见 R-05）。

## R-04 现有 API 的约束

**决策**：不破坏 `Scenario` 直接构造的用法，新增能力挂在 pytest 集成层。

**依据（读源码）**：

- `pytest_plugin.py` 目前只提供 `replayguard` fixture，返回 `Scenario` **类本身**
  （`return Scenario`），不做任何生命周期管理。
- `Scenario.finish()` 是幂等的（`if self._report is not None: return self._report`），
  可被 teardown 安全重复调用。
- 全仓 34 个文件、80 处 `finish()` 中，绝大多数直接 `Scenario(...)` 构造，**只有 3 处**
  用 `replayguard` fixture（`tests/contract/test_pytest_plugin.py`）。
- 因此：把自动断言做进 `replayguard` fixture 影响面极小；但要真正覆盖用户，fixture 必须
  能被方便地使用。

## R-05 关键设计约束：避免「失败叠加噪音」

**决策**：teardown 自动断言只在**测试体未失败**时生效；测试体已失败则只补充诊断信息、
不再额外抛错。

**依据**：R-03 实测的「1 failed + 1 error」会让报告难读，且把「用户业务断言失败」与
「副作用违规」混为一谈。实现上可用 pytest hook（`pytest_runtest_makereport`）读取当前
用例的 body 结果，或更简单地：在 fixture 中捕获并比对 `sys.exc_info()` / 通过
`request.node` 的 `rep_call` 状态判断。

**备选方案与否决理由**：

| 方案 | 否决理由 |
|------|----------|
| 在 `Scenario.finish()` 里直接抛异常 | 破坏「finish 只产出报告」的语义；用户需要拿到 report 做细粒度断言（如 `committed_count`），强制抛错会让这类用法无法写 |
| 在 `Scenario.__del__` 里检查 | 析构时机不确定、异常被吞、不可复现（违反宪法 II） |
| 要求用户 `@pytest.mark.usefixtures` 手动挂 | 仍是「靠记忆」，没解决根因 |
| 全局 autouse fixture 扫描所有 Scenario | 影响所有测试（含不用本工具的），且与「不执行全局补丁」的既有约定冲突 |

## R-06 与宪法的对照

| 原则 | 对照结论 |
|------|----------|
| I 真实需求优先 | ✅ R-01/R-02 为实测证据，非假设 |
| II 确定性可复现 | ✅ 自动断言只读已有确定性报告，不引入时间/随机 |
| III 默认模拟外部服务 | ✅ 无外部依赖，纯进程内 |
| IV 测试先行 | ✅ 必须先在 teardown 场景写失败测试 |
| V 小接口面 | ✅ 不新增公开类；只增强现有 fixture 行为，需评估 SemVer |
| VI 模块化边界 | ✅ 改动集中在 `pytest_plugin.py`（集成层），不碰核心模块语义 |
| VII 克制范围 | ✅ 只解决「忘记断言」，不做自动修复、不做报告平台 |
| VIII 失败可解释 | ✅ 自动断言失败时必须复用 `report.format()` 的定位信息 |

## R-07 竞品复核（宪法 I 要求）

**决策**：确认这是本工具特有的缺口，不是已被通用方案覆盖的问题。

**结论**：通用测试库（pytest 本身、hypothesis、pytest-mock）都**不会**在测试结束后自动
检查「业务副作用是否重复」——它们没有业务键与提交语义的概念。因此「忘记断言导致漏报」
在副作用安全领域是本工具独有的风险点，需要自己解决。

**证据等级说明**：本条为基于生态惯例的**合理推断**（未做逐一手工核验），在 spec 中标注
为推断而非已核实事实。
