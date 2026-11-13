"""JUnit XML 导出测试。"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from agentreplayguard import (
    CustomInvariant,
    FaultKind,
    FaultPlan,
    FaultRule,
    NoDuplicateEffects,
    Scenario,
)


def _make_violating_report():
    scenario = Scenario(
        "junit",
        seed=7,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id")
    def refund(refund_id: str) -> str:
        return f"refunded {refund_id}"

    for _ in range(2):
        try:
            refund("R-1")
        except TimeoutError:
            continue

    return scenario.finish()


def test_violation_maps_to_failure_testcase():
    report = _make_violating_report()
    xml = report.to_junit_xml()

    root = ET.fromstring(xml)
    assert root.tag == "testsuite"
    assert root.get("name") == "junit"
    assert int(root.get("failures")) == len(report.violations)

    failure_cases = [c for c in root.findall("testcase") if c.find("failure") is not None]
    assert len(failure_cases) == len(report.violations)
    for case in failure_cases:
        failure = case.find("failure")
        assert failure is not None
        assert failure.get("type") == "no_duplicate_effects:refund"


def test_clean_report_produces_passing_testcase():
    scenario = Scenario("clean", seed=0, invariants=[NoDuplicateEffects("refund")])
    scenario.guard().call("refund", lambda: None, key=lambda a: "R-1")
    report = scenario.finish()

    xml = report.to_junit_xml()
    root = ET.fromstring(xml)

    assert root.get("name") == "clean"
    assert int(root.get("failures")) == 0
    cases = root.findall("testcase")
    assert len(cases) == 1
    assert cases[0].get("name") == "effects_safety"
    assert cases[0].find("failure") is None


def test_xml_is_parseable_and_counts_consistent():
    report = _make_violating_report()
    root = ET.fromstring(report.to_junit_xml())

    n_violations = len(report.violations)
    assert int(root.get("tests")) == n_violations
    assert int(root.get("failures")) == n_violations
    assert len(root.findall("testcase")) == n_violations


def test_special_characters_escaped():
    scenario = Scenario(
        "special",
        seed=0,
        invariants=[CustomInvariant("bad<&\"", lambda view: False, message="msg <a>&\"b")],
    )
    report = scenario.finish()
    assert report.violations  # 有 violation

    xml = report.to_junit_xml()
    # 必须能解析（转义正确）
    root = ET.fromstring(xml)
    failure = root.find("testcase/failure")
    assert failure is not None
    # 解析后能还原原始文本（转义无损）
    assert "<a>&" in (failure.get("message") or "")
    assert 'bad<&"' in (failure.get("type") or "")


def test_deterministic_output():
    a = _make_violating_report().to_junit_xml()
    b = _make_violating_report().to_junit_xml()
    assert a == b


def test_time_is_fixed_zero():
    report = _make_violating_report()
    root = ET.fromstring(report.to_junit_xml())
    assert root.get("time") == "0.0"
