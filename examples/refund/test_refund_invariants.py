"""US5 独立验收：用业务不变量声明「应该发生什么」。"""

from __future__ import annotations

from agentreplayguard import CustomInvariant, MaxEffectCount, Scenario

from .tools import make_tools


def test_max_effect_count_reports_expected_actual():
    scenario = Scenario("refund-max-count", invariants=[MaxEffectCount("refund", 1)])
    refund, _notify, _service = make_tools(scenario)

    refund("R-1", 100)
    refund("R-2", 100)

    report = scenario.finish()
    assert not report.ok
    violation = report.violations[0]
    assert violation.invariant_name == "max_effect_count:refund"
    assert violation.expected == 1
    assert violation.actual == 2


def test_custom_invariant_passes():
    def at_most_two(view):
        return view.committed_count("refund") <= 2

    scenario = Scenario(
        "refund-custom-pass",
        invariants=[CustomInvariant("at_most_two_refunds", at_most_two)],
    )
    refund, _notify, _service = make_tools(scenario)
    refund("R-1", 100)

    report = scenario.finish()
    assert report.ok


def test_custom_invariant_fails():
    def exactly_one(view):
        return view.committed_count("refund") == 1

    scenario = Scenario(
        "refund-custom-fail",
        invariants=[CustomInvariant("exactly_one_refund", exactly_one)],
    )
    refund, _notify, _service = make_tools(scenario)
    refund("R-1", 100)
    refund("R-2", 100)

    report = scenario.finish()
    assert not report.ok
    violation = report.violations[0]
    assert violation.invariant_name == "exactly_one_refund"
    assert violation.expected is True
    assert violation.actual is False
