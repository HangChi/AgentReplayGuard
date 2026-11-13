"""HttpEffect 抽取到共享模块后的契约测试。"""

from __future__ import annotations

import pytest

from agentreplayguard import ScenarioConfigError
from agentreplayguard.adapters._http_common import HttpEffect, classify_or_raise


def test_http_effect_from_common_equals_httpx_export():
    from agentreplayguard.adapters.httpx import HttpEffect as HttpxHttpEffect

    assert HttpEffect is HttpxHttpEffect


def test_http_effect_validation():
    with pytest.raises(ScenarioConfigError):
        HttpEffect(effect_type="", business_key="k", params={})
    with pytest.raises(ScenarioConfigError):
        HttpEffect(effect_type="t", business_key="", params={})
    with pytest.raises(ScenarioConfigError):
        HttpEffect(effect_type="t", business_key="k", params="not-mapping")  # type: ignore
    with pytest.raises(ScenarioConfigError):
        HttpEffect(effect_type="t", business_key="k", params={}, idempotency_key=1)  # type: ignore


def test_classify_or_raise_passthrough_and_none():
    class Req:
        method = "GET"
        url = "http://x"

    assert classify_or_raise(lambda r: None, Req()) is None

    effect = HttpEffect("refund", "R-1", {})
    assert classify_or_raise(lambda r: effect, Req()) is effect


def test_classify_or_raise_wraps_exception():
    class Req:
        method = "POST"
        url = "http://x"

    def bad(r):
        raise ValueError("boom")

    with pytest.raises(ScenarioConfigError) as exc:
        classify_or_raise(bad, Req())
    assert "classify failed" in str(exc.value)


def test_classify_or_raise_rejects_wrong_type():
    class Req:
        method = "GET"
        url = "http://x"

    with pytest.raises(ScenarioConfigError):
        classify_or_raise(lambda r: "not-an-effect", Req())  # type: ignore
