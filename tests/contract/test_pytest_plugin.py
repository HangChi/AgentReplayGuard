"""US6 契约测试：replayguard fixture。

013 起 fixture 返回**场景工厂**（而非 `Scenario` 类本身），以便登记实例做自动断言。
调用写法 `replayguard("name", ...)` 保持不变。
"""

from __future__ import annotations

from agentreplayguard import Scenario
from agentreplayguard.pytest_plugin import _ScenarioFactory


def test_replayguard_plugin_registered(pytestconfig):
    names = {name for name, _ in pytestconfig.pluginmanager.list_name_plugin()}
    assert "agentreplayguard" in names


def test_replayguard_returns_callable_factory(replayguard):
    assert callable(replayguard)
    assert isinstance(replayguard, _ScenarioFactory)


def test_replayguard_creates_fresh_instances(replayguard):
    first = replayguard("first")
    second = replayguard("second")
    assert isinstance(first, Scenario)
    assert isinstance(second, Scenario)
    assert first is not second
    assert first.name == "first"
    assert second.name == "second"


def test_replayguard_accepts_scenario_arguments(replayguard):
    """工厂签名需与 `Scenario.__init__` 的关键字参数保持一致。"""
    scenario = replayguard("args", seed=7, invariants=[])
    assert scenario.name == "args"
    assert scenario.seed == 7
