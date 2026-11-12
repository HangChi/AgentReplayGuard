"""US6 契约测试：replayguard fixture。"""

from __future__ import annotations

from agentreplayguard import Scenario


def test_replayguard_plugin_registered(pytestconfig):
    names = {name for name, _ in pytestconfig.pluginmanager.list_name_plugin()}
    assert "agentreplayguard" in names


def test_replayguard_returns_scenario_constructor(replayguard):
    assert replayguard is Scenario


def test_replayguard_creates_fresh_instances(replayguard):
    first = replayguard("first")
    second = replayguard("second")
    assert first is not second
    assert first.name == "first"
    assert second.name == "second"
