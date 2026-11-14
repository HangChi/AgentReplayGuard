# Implementation Plan: 场景自动断言（消除静默漏报）

**Branch**: `013-auto-assert-scenario` | **Date**: 2026-11-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/013-auto-assert-scenario/spec.md`

## Summary

把「是否断言」从调用方的记忆力，改为工具的责任：`replayguard` fixture 在测试结束后自动
检查该测试创建的所有场景，有违规就让测试失败。技术路径是 pytest fixture 的 `yield` 后置段
（teardown）——它无论测试体通过、失败还是抛异常都会执行（research R-03 已实测）。

关键设计约束：teardown 抛错在 pytest 里表现为 **ERROR**，若测试体已失败还会叠加
「1 failed + 1 error」噪音（research R-05 实测）。因此自动断言只在测试体未失败时抛错，
测试体已失败时降级为 warning。

## Technical Context

**Language/Version**: Python ≥ 3.10（与现有一致）

**Primary Dependencies**: 核心零第三方依赖；pytest 是测试期依赖（已有 `pytest11` entry point）

**Storage**: N/A（纯内存）

**Testing**: pytest；测试先行（宪法 IV）

**Target Platform**: Linux / macOS

**Project Type**: library（pytest 插件形态）

**Constraints**:
- 不引入第三方依赖
- 不修改核心模块语义（宪法 VI）：`Scenario` / `EffectStore` / `Invariant` 不动
- 确定性：自动断言只读已有报告，不引入时间/随机（宪法 II）
- 不改 `Scenario(...)` 直接构造的既有行为（FR-006）

**Scale/Scope**: 改动集中在 `src/agentreplayguard/pytest_plugin.py`（约 60–90 行）+ 测试

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 门禁问题 | 结论 |
|------|----------|------|
| I 真实需求优先 | 有实测证据吗？ | ✅ 4 个探针实测 + 全仓 80/6 统计（research R-01/R-02） |
| II 确定性可复现 | 引入不确定性了吗？ | ✅ 无；只读确定性报告 |
| III 默认模拟外部服务 | 调用真实服务了吗？ | ✅ 无网络、无外部依赖 |
| IV 测试先行 | 先写失败测试了吗？ | ✅ tasks 中 T003 先写「漏报必须失败」的测试 |
| V 小接口面 | 公开 API 变更受控吗？ | ⚠️ `replayguard` fixture 从「返回 Scenario 类」改为「返回工厂函数」，属**可感知变更** → 版本 0.12.0 → 0.13.0，需迁移说明 |
| VI 模块化边界 | 改了核心模块语义吗？ | ✅ 只改 `pytest_plugin.py`（集成层） |
| VII 克制范围 | 有更简单的替代吗？ | ✅ 见 research R-05 的否决方案表；本方案是最小可行 |
| VIII 失败可解释 | 失败信息可定位吗？ | ✅ 复用 `ScenarioReport.format()`，含业务键/尝试/状态 |

**V 的处理**：`replayguard is Scenario` 是既有契约（`tests/contract/test_pytest_plugin.py`
第 13-14 行断言）。改为工厂函数后该断言失效。这是**有意变更**：因为「返回类本身」无法
登记实例，也就无法自动检查。迁移成本极低（调用写法 `replayguard("name", ...)` 完全不变），
但必须：
1. 更新该契约测试为「调用后得到 Scenario 实例」；
2. 在 CHANGELOG 记录为 Changed，并说明调用写法不变；
3. 版本 bump 到 0.13.0（MINOR）。

## Project Structure

### Documentation (this feature)

```text
specs/013-auto-assert-scenario/
├── research.md      # 缺陷证据、生态方案、否决方案、宪法对照
├── spec.md          # 3 个用户故事、8 条 FR、5 条 SC
├── plan.md          # 本文件
└── tasks.md         # 任务清单
```

### Source Code

```text
src/agentreplayguard/
└── pytest_plugin.py        # 唯一改动文件：fixture 改为生命周期管理工厂

tests/
├── contract/
│   └── test_pytest_plugin.py       # 更新既有契约断言
└── unit/
    └── test_auto_assert.py         # 新增：漏报/兼容/预期违规/skip-xfail 全覆盖
```

**Structure Decision**: 单文件改动 + 一个新测试文件。不新增模块，不新增公开类（宪法 VII）。

## 设计要点

### 1. fixture 形态

```python
@pytest.fixture
def replayguard(request):
    created: list[Scenario] = []
    def factory(name, *, seed=0, faults=None, invariants=(), expect_violations=False):
        scenario = Scenario(name, seed=seed, faults=faults, invariants=invariants)
        created.append(scenario)
        return scenario
    yield factory
    # teardown: 逐个检查
```

`expect_violations=True` 满足 FR-005（元测试可写）。该参数由 factory 消费，不传给
`Scenario`，因此核心构造签名不变。

### 2. teardown 判定顺序（FR-002/003/004）

对每个登记的场景：

1. `report = scenario.finish()`（幂等，用户已调用也无副作用）
2. 若 `report.ok` → 继续下一个
3. 若 `expect_violations=True` → 视为通过，继续
4. 若测试体已失败（`request.node.rep_call.failed`）→ `warnings.warn(...)` 附加诊断，不抛错
5. 否则 → 抛出 `EffectSafetyError(report.format())`

**FR-003 如何满足**：用户若已 `assert not report.ok`，测试体就会失败 → 落到第 4 步，
不重复抛错。若用户已 `assert_clean()` 且场景确实干净，则第 2 步就通过。

### 3. 「场景未运行」的处理（Edge Case）

若场景被创建但 `len(report.effects) == 0` 且未声明 `expect_violations`，给一条 warning
（不失败）：`scenario '<name>' was created but recorded no effects`。避免「声明了却没用」
完全不留痕迹。

### 4. skip / xfail 兼容（FR-007）

`request.node.rep_call` 在 skip 时为 `skipped`；teardown 里若 `rep_call.skipped` 则直接
返回，不做检查。xfail 时 `rep_call.failed` 为 False 但 `wasxfail` 存在 → 也应跳过检查，
避免把「预期失败」变成 ERROR。

## Complexity Tracking

无宪法违规需要论证的复杂度。改动是**减少**复杂度（少一行用户代码）。
