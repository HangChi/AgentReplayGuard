"""pytest 插件入口：提供 `replayguard` fixture 与自动断言。

通过 `pyproject.toml` 的 `[project.entry-points.pytest11]` 自动注册。

**自动断言**：fixture 登记测试内创建的所有场景，测试体执行完毕后自动检查——有副作用违规
就让测试 **FAILED**。这样「忘记写断言」不再等于「静默通过」（见
specs/013-auto-assert-scenario）。

接入点选在 `pytest_runtest_call`（测试体跑完、fixture teardown 之前）：

- 若放在 fixture 的 teardown 里抛异常，pytest 记为 **ERROR**，报告呈现为
  「1 passed, 1 error」，容易被误读为插件自身故障。
- 若在 `pytest_runtest_makereport` 里改写 call 报告，此时该报告**已经上报**，改写无效。

`pytest_runtest_call` 阶段抛异常会被记为 **FAILED**，且能读取测试体是否已经失败，从而
避免「1 failed + 1 error」的噪音叠加。

判定顺序（对每个登记的场景）：
1. 报告无违规 → 通过。
2. 声明了 `expect_violations=True` → 视为通过（用于「验证工具能抓到问题」的元测试）。
3. 测试体已失败 / 已 skip / 已 xfail → 只补诊断 warning，不追加错误。
4. 其余情况 → 抛 `ScenarioViolation`，由 pytest 记为 FAILED，信息复用
   `ScenarioReport.format()` 的定位内容。
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Generator, Sequence
from typing import Any

import pytest

from .faults import FaultPlan
from .invariants import Invariant
from .scenario import Scenario

_EMPTY_EFFECTS_WARNING = (
    "replayguard scenario {name!r} was created but recorded no effects; "
    "did the workflow actually run?"
)

_FACTORY_ARGNAME = "replayguard"


class ScenarioViolation(AssertionError):
    """副作用违规：由插件在测试体结束后抛出，pytest 记为 FAILED。"""


class _ScenarioFactory:
    """`replayguard` fixture 返回的工厂：登记场景，供测试结束后统一检查。

    调用签名与 `Scenario.__init__` 保持一致（`name` + 关键字参数），因此既有写法
    `replayguard("name", seed=0, ...)` 无需修改。额外支持 `expect_violations`。
    """

    def __init__(self) -> None:
        self._created: list[tuple[Scenario, bool]] = []

    def __call__(
        self,
        name: str,
        *,
        seed: int = 0,
        faults: FaultPlan | None = None,
        invariants: Sequence[Invariant] = (),
        expect_violations: bool = False,
    ) -> Scenario:
        scenario = Scenario(name, seed=seed, faults=faults, invariants=invariants)
        self._created.append((scenario, expect_violations))
        return scenario

    def _first_violation_message(self) -> str | None:
        """返回第一个违规场景的报告文本；无违规则返回 None。"""
        for scenario, expect_violations in self._created:
            report = scenario.finish()
            if report.ok or expect_violations:
                continue
            return report.format()
        return None

    def _empty_effect_warnings(self) -> list[str]:
        """场景被创建但没记录任何 effect 时给出提示（不失败）。"""
        return [
            _EMPTY_EFFECTS_WARNING.format(name=scenario.name)
            for scenario, _expect in self._created
            if not scenario.finish().effects
        ]


@pytest.fixture
def replayguard() -> Generator[Callable[..., Scenario], None, None]:
    """返回场景工厂；测试结束后自动检查所有已创建场景的副作用安全性。"""
    yield _ScenarioFactory()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, Any, Any]:
    """测试体执行完毕后，检查该测试创建的场景是否出现副作用违规。

    用新版 `wrapper=True` 而非旧版 `hookwrapper=True`：后者在 teardown 段抛异常会触发
    `PluggyTeardownRaisedWarning` 噪音，前者不会。
    """
    try:
        result = yield
    except BaseException:
        # 测试体自身已抛异常：副作用结论只能作为附加诊断，不覆盖原失败原因。
        _warn_if_violated(item)
        raise

    # `funcargs` 只存在于 Function 子类上，故用 getattr 安全访问。
    funcargs: dict[str, Any] = getattr(item, "funcargs", {})
    factory = funcargs.get(_FACTORY_ARGNAME)
    if not isinstance(factory, _ScenarioFactory):
        return result

    violation_message = factory._first_violation_message()
    if violation_message is not None:
        raise ScenarioViolation(violation_message)

    for message in factory._empty_effect_warnings():
        warnings.warn(message, stacklevel=2)
    return result


def _warn_if_violated(item: pytest.Item) -> None:
    """测试体已失败时，把副作用违规降级为 warning 附加诊断。"""
    funcargs: dict[str, Any] = getattr(item, "funcargs", {})
    factory = funcargs.get(_FACTORY_ARGNAME)
    if not isinstance(factory, _ScenarioFactory):
        return
    violation_message = factory._first_violation_message()
    if violation_message is not None:
        warnings.warn(
            f"side-effect violations also detected: {violation_message}",
            stacklevel=3,
        )
