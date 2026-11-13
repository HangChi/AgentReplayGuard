"""JUnit XML 报告生成：把 ScenarioReport 转为 CI 原生解析的 JUnit XML。

仅依赖标准库；`time` 属性固定为 0.0 以保证确定性（本工具的「时间」是逻辑 tick，非墙钟）。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .report import ScenarioReport

__all__ = ["to_junit_xml"]

_TIME = "0.0"


def to_junit_xml(report: ScenarioReport) -> str:
    """把场景报告转为 JUnit XML 字符串。

    一个 scenario 映射为一个 ``testsuite``；每个 violation 映射为一个带 ``<failure>`` 的
    ``testcase``；无 violation 时产出一个通过的 ``testcase``。
    """
    violations = report.violations
    tests = len(violations) if violations else 1

    suite = ET.Element(
        "testsuite",
        {
            "name": report.scenario_name,
            "tests": str(tests),
            "failures": str(len(violations)),
            "errors": "0",
            "time": _TIME,
        },
    )

    if violations:
        for violation in violations:
            case = ET.SubElement(
                suite,
                "testcase",
                {
                    "name": violation.invariant_name,
                    "classname": report.scenario_name,
                    "time": _TIME,
                },
            )
            failure = ET.SubElement(
                case,
                "failure",
                {
                    "message": violation.message,
                    "type": violation.invariant_name,
                },
            )
            if violation.effect_ids:
                failure.text = "effects: " + ", ".join(violation.effect_ids)
    else:
        ET.SubElement(
            suite,
            "testcase",
            {
                "name": "effects_safety",
                "classname": report.scenario_name,
                "time": _TIME,
            },
        )

    return ET.tostring(suite, encoding="unicode")
