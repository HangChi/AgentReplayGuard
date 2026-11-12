"""HttpEffect 值对象的校验规则。"""

from __future__ import annotations

from typing import Any

import pytest

from agentreplayguard import ScenarioConfigError
from agentreplayguard.adapters.httpx import HttpEffect


def test_valid_effect_defaults_idempotency_key_to_none():
    effect = HttpEffect(effect_type="refund", business_key="R-1", params={"amount_cents": 100})
    assert effect.effect_type == "refund"
    assert effect.business_key == "R-1"
    assert effect.params == {"amount_cents": 100}
    assert effect.idempotency_key is None


def test_valid_effect_accepts_idempotency_key():
    effect = HttpEffect(
        effect_type="refund",
        business_key="R-1",
        params={},
        idempotency_key="idem-1",
    )
    assert effect.idempotency_key == "idem-1"


@pytest.mark.parametrize("effect_type", ["", None, 3])
def test_effect_type_must_be_non_empty_str(effect_type: Any):
    with pytest.raises(ScenarioConfigError, match="effect_type"):
        HttpEffect(effect_type=effect_type, business_key="R-1", params={})


@pytest.mark.parametrize("business_key", ["", None, 3])
def test_business_key_must_be_non_empty_str(business_key: Any):
    with pytest.raises(ScenarioConfigError, match="business_key"):
        HttpEffect(effect_type="refund", business_key=business_key, params={})


@pytest.mark.parametrize("params", [None, [], "x"])
def test_params_must_be_mapping(params: Any):
    with pytest.raises(ScenarioConfigError, match="params"):
        HttpEffect(effect_type="refund", business_key="R-1", params=params)


def test_idempotency_key_must_be_str_or_none():
    with pytest.raises(ScenarioConfigError, match="idempotency_key"):
        HttpEffect(
            effect_type="refund",
            business_key="R-1",
            params={},
            idempotency_key=3,  # type: ignore[arg-type]
        )
