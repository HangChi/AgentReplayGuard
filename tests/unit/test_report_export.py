"""ScenarioReport 结构化导出（to_dict/to_json）测试。"""

from __future__ import annotations

import json

from agentreplayguard import (
    FaultKind,
    FaultPlan,
    FaultRule,
    NoDuplicateEffects,
    Scenario,
)


def _make_report():
    scenario = Scenario(
        "export",
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


def test_to_dict_is_json_serializable():
    report = _make_report()
    d = report.to_dict()
    # 不抛异常即可 JSON 序列化
    json.dumps(d)
    assert d["scenario_name"] == "export"
    assert d["seed"] == 7
    assert isinstance(d["effects"], list)
    assert isinstance(d["violations"], list)


def test_to_dict_enum_to_value():
    report = _make_report()
    d = report.to_dict()
    effect = d["effects"][0]
    # Enum 转 value 字符串
    assert effect["status"] == "committed"
    assert effect["fault"] == "timeout_after_commit"


def test_to_dict_fault_none_preserved():
    scenario = Scenario("no-fault", seed=0, invariants=[NoDuplicateEffects("x")])
    scenario.guard().call("x", lambda: None, key=lambda a: "k")
    d = scenario.finish().to_dict()
    assert d["effects"][0]["fault"] is None


def test_to_json_parses_and_matches_dict():
    report = _make_report()
    s = report.to_json()
    parsed = json.loads(s)
    assert parsed == report.to_dict()


def test_to_json_deterministic():
    a = _make_report().to_json()
    b = _make_report().to_json()
    assert a == b


def test_empty_report_ok():
    scenario = Scenario("empty", seed=0)
    d = scenario.finish().to_dict()
    assert d["effects"] == []
    assert d["violations"] == []
    assert d["warnings"] != []  # 无 invariant 会有一条 warning


def test_format_and_assert_clean_unchanged():
    report = _make_report()
    # format 仍可用
    text = report.format()
    assert "Scenario: export" in text
    # assert_clean 仍会抛（有 violation）
    import pytest

    from agentreplayguard import EffectSafetyError

    with pytest.raises(EffectSafetyError):
        report.assert_clean()
