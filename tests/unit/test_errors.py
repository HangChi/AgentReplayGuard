from __future__ import annotations

from agentreplayguard import (
    EffectSafetyError,
    PartialSuccessError,
    ScenarioConfigError,
    ScenarioStateError,
    ServiceError,
    UnsupportedGraphError,
)
from agentreplayguard.services.refund import IdempotencyConflict


def test_effect_safety_error_is_assertion_error():
    assert issubclass(EffectSafetyError, AssertionError)


def test_scenario_config_error_is_value_error():
    assert issubclass(ScenarioConfigError, ValueError)


def test_scenario_state_error_is_runtime_error():
    assert issubclass(ScenarioStateError, RuntimeError)


def test_unsupported_graph_error_is_runtime_error():
    assert issubclass(UnsupportedGraphError, RuntimeError)


def test_service_error_carries_status():
    err = ServiceError(status=500)
    assert err.status == 500


def test_partial_success_error_is_exception():
    assert issubclass(PartialSuccessError, Exception)


def test_idempotency_conflict_is_exception():
    assert issubclass(IdempotencyConflict, Exception)
