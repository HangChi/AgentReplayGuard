from __future__ import annotations

from agentreplayguard import (
    CustomInvariant,
    EffectGuard,
    EffectRecord,
    EffectSafetyError,
    EffectStatus,
    EffectStore,
    EffectView,
    FaultKind,
    FaultPlan,
    FaultRule,
    GraphRun,
    Invariant,
    MaxEffectCount,
    NoDuplicateEffects,
    PartialSuccessError,
    RunInputKind,
    RunSegment,
    Scenario,
    ScenarioConfigError,
    ScenarioReport,
    ScenarioStateError,
    ServiceError,
    UnsupportedGraphError,
    Violation,
)
from agentreplayguard.services.refund import IdempotencyConflict, Refund, SimulatedRefundService


def test_public_import_surface():
    # 所有公开符号均可从顶层包导入
    names = [
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
    ]
    for name in names:
        assert name is not None


def test_refund_import_surface():
    assert SimulatedRefundService is not None
    assert Refund is not None
    assert IdempotencyConflict is not None


def test_scenario_lifecycle():
    scenario = Scenario("s", invariants=[NoDuplicateEffects()])
    report = scenario.finish()
    assert report.ok
    assert report.scenario_name == "s"


def test_guard_effect_signature_preserved():
    scenario = Scenario("s")

    @scenario.guard().effect("refund", key="refund_id")
    def refund(refund_id: str) -> str:
        return refund_id

    assert refund("R-1") == "R-1"
    assert refund.__name__ == "refund"
