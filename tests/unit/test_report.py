from __future__ import annotations

import pytest

from agentreplayguard import (
    EffectSafetyError,
    EffectStatus,
    GraphRun,
    RunInputKind,
    RunSegment,
    ScenarioReport,
)
from agentreplayguard.effects import EffectRecord
from agentreplayguard.invariants import Violation


def make_effect(effect_id: str = "eff-000001", sequence: int = 1) -> EffectRecord:
    return EffectRecord(
        effect_id=effect_id,
        sequence=sequence,
        effect_type="refund",
        business_key="R-1",
        params_hash="h",
        idempotency_key_hash=None,
        attempt=1,
        status=EffectStatus.COMMITTED,
        fault=None,
        error_type=None,
        error_message=None,
        run_id=None,
        thread_id=None,
        checkpoint_id=None,
        started_tick=0,
        ended_tick=1,
    )


def test_report_ok():
    assert ScenarioReport("s", 0, (), (), (), ()).ok


def test_report_not_ok_with_violation():
    violation = Violation("inv", "msg", 1, 2, ("eff-000001",))
    assert not ScenarioReport("s", 0, (), (), (violation,), ()).ok


def test_assert_clean_raises():
    violation = Violation("inv", "msg", 1, 2, ())
    report = ScenarioReport("s", 0, (), (), (violation,), ())
    with pytest.raises(EffectSafetyError) as excinfo:
        report.assert_clean()
    assert "inv" in str(excinfo.value)


def test_format_is_deterministic():
    effect = make_effect()
    first = ScenarioReport("s", 0, (effect,), (), (), ())
    second = ScenarioReport("s", 0, (effect,), (), (), ())
    assert first.format() == second.format()


def test_format_includes_warnings():
    report = ScenarioReport("s", 0, (), (), (), ("no invariants declared",))
    assert "no invariants declared" in report.format()


def test_run_segment_and_graph_run():
    segment = RunSegment(
        "run-0001",
        "thread-0001",
        RunInputKind.START,
        None,
        None,
        1,
        2,
        False,
        None,
        None,
    )
    graph_run = GraphRun(segment, {}, ())
    assert not graph_run.interrupted
    assert graph_run.output == {}
