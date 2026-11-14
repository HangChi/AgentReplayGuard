"""013 自动断言：漏报必须让测试失败。

这些测试用 `pytester` 在嵌套 pytest 会话里跑「用户写法」，验证真实运行结果。
在自动断言实现之前，本文件应当全部失败（宪法 IV 测试先行）。
"""

from __future__ import annotations

import pytest

# 嵌套会话里使用的公共片段：造一个会重复退款的场景
_DUP_REFUND_SETUP = """
from agentreplayguard import (
    FaultKind,
    FaultPlan,
    FaultRule,
    NoDuplicateEffects,
)


def _dup_refund(replayguard, **kwargs):
    scenario = replayguard(
        "dup-refund",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
        **kwargs,
    )
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id")
    def refund(refund_id: str) -> str:
        return refund_id

    for _ in range(2):
        try:
            refund("R-1")
        except TimeoutError:
            pass
    return scenario
"""


def test_forgot_finish_fails(pytester: pytest.Pytester) -> None:
    """R-01 P1：忘记调用 finish()，重复副作用必须让测试失败。"""
    pytester.makepyfile(
        test_forgot=_DUP_REFUND_SETUP
        + """
def test_forgot_finish(replayguard):
    _dup_refund(replayguard)
    # 故意不调用 scenario.finish()
"""
    )
    result = pytester.runpytest("-q")
    result.assert_outcomes(failed=1)


def test_finish_without_assert_fails(pytester: pytest.Pytester) -> None:
    """R-01 P2：调用了 finish() 但没断言，重复副作用仍必须失败。"""
    pytester.makepyfile(
        test_noassert=_DUP_REFUND_SETUP
        + """
def test_finish_no_assert(replayguard):
    scenario = _dup_refund(replayguard)
    report = scenario.finish()
    assert report.ok is False or True  # 无实质断言
"""
    )
    result = pytester.runpytest("-q")
    result.assert_outcomes(failed=1)


def test_unused_scenario_warns(pytester: pytest.Pytester) -> None:
    """R-01 P3：声明了场景却完全没用，不应完全静默（给 warning）。"""
    pytester.makepyfile(
        test_unused="""
def test_unused(replayguard):
    replayguard("never-used", seed=0)
"""
    )
    result = pytester.runpytest("-q")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*never-used*no effects*"])


def test_clean_scenario_passes(pytester: pytest.Pytester) -> None:
    """无违规场景不应产生误报。"""
    pytester.makepyfile(
        test_clean="""
from agentreplayguard import NoDuplicateEffects


def test_clean(replayguard):
    scenario = replayguard("clean", seed=0, invariants=[NoDuplicateEffects("refund")])
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id")
    def refund(refund_id: str) -> str:
        return refund_id

    refund("R-1")  # 只提交一次
"""
    )
    result = pytester.runpytest("-q")
    result.assert_outcomes(passed=1)


def test_expect_violations_allows_duplicates(pytester: pytest.Pytester) -> None:
    """FR-005：显式声明预期违规时，元测试应能通过。"""
    pytester.makepyfile(
        test_meta=_DUP_REFUND_SETUP
        + """
def test_meta(replayguard):
    _dup_refund(replayguard, expect_violations=True)
"""
    )
    result = pytester.runpytest("-q")
    result.assert_outcomes(passed=1)


def test_body_failure_not_doubled(pytester: pytest.Pytester) -> None:
    """FR-004：测试体已失败时，不追加第二个 error。"""
    pytester.makepyfile(
        test_double=_DUP_REFUND_SETUP
        + """
def test_body_fails(replayguard):
    _dup_refund(replayguard)
    assert 1 == 2
"""
    )
    result = pytester.runpytest("-q")
    result.assert_outcomes(failed=1)
    result.stdout.no_fnmatch_line("*1 failed, 1 error*")


def test_explicit_assert_not_doubled(pytester: pytest.Pytester) -> None:
    """FR-003：用户已显式断言时，不重复报错。"""
    pytester.makepyfile(
        test_explicit=_DUP_REFUND_SETUP
        + """
def test_explicit_assert(replayguard):
    scenario = _dup_refund(replayguard)
    report = scenario.finish()
    assert not report.ok
"""
    )
    result = pytester.runpytest("-q")
    result.assert_outcomes(failed=1)


def test_skip_is_not_turned_into_error(pytester: pytest.Pytester) -> None:
    """FR-007：skip 语义不受影响。"""
    pytester.makepyfile(
        test_skip=_DUP_REFUND_SETUP
        + """
import pytest


@pytest.mark.skip(reason="intentional")
def test_skipped(replayguard):
    _dup_refund(replayguard)
"""
    )
    result = pytester.runpytest("-q")
    result.assert_outcomes(skipped=1)


def test_xfail_is_not_turned_into_error(pytester: pytest.Pytester) -> None:
    """FR-007：xfail 语义不受影响。"""
    pytester.makepyfile(
        test_xfail=_DUP_REFUND_SETUP
        + """
import pytest


@pytest.mark.xfail(reason="intentional")
def test_xfailed(replayguard):
    _dup_refund(replayguard)
    raise AssertionError("expected")
"""
    )
    result = pytester.runpytest("-q")
    result.assert_outcomes(xfailed=1)


def test_multiple_scenarios_all_checked(pytester: pytest.Pytester) -> None:
    """同一测试内多个场景都要被检查。"""
    pytester.makepyfile(
        test_multi=_DUP_REFUND_SETUP
        + """
def test_multi(replayguard):
    _dup_refund(replayguard)
    _dup_refund(replayguard)
"""
    )
    result = pytester.runpytest("-q")
    result.assert_outcomes(failed=1)
