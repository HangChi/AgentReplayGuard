"""运行报告：RunSegment、GraphRun 与 ScenarioReport。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from typing import Any

from .effects import EffectRecord
from .errors import EffectSafetyError
from .invariants import Violation


class RunInputKind(str, Enum):
    START = "start"
    RESUME = "resume"
    INTERRUPT_RESUME = "interrupt_resume"


@dataclass(frozen=True)
class RunSegment:
    run_id: str
    thread_id: str
    input_kind: RunInputKind
    checkpoint_before: str | None
    checkpoint_after: str | None
    started_tick: int
    ended_tick: int
    interrupted: bool
    error_type: str | None
    error_message: str | None


@dataclass(frozen=True)
class GraphRun:
    segment: RunSegment
    output: Mapping[str, Any] | None
    interrupts: tuple[Any, ...]

    @property
    def interrupted(self) -> bool:
        return self.segment.interrupted


@dataclass(frozen=True)
class ScenarioReport:
    scenario_name: str
    seed: int
    effects: tuple[EffectRecord, ...]
    run_segments: tuple[RunSegment, ...]
    violations: tuple[Violation, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.violations

    def format(self) -> str:
        lines: list[str] = [f"Scenario: {self.scenario_name} (seed={self.seed})"]
        for warning in self.warnings:
            lines.append(f"warning: {warning}")
        for effect in self.effects:
            lines.append(self._format_effect(effect))
        if self.violations:
            lines.append("violations:")
            for violation in self.violations:
                lines.append(
                    f"  [{violation.invariant_name}] {violation.message} "
                    f"(expected={violation.expected!r}, actual={violation.actual!r}, "
                    f"effects={list(violation.effect_ids)})"
                )
        else:
            lines.append("ok: no violations")
        return "\n".join(lines)

    def assert_clean(self) -> None:
        if not self.ok:
            raise EffectSafetyError(self.format())

    def to_dict(self) -> dict[str, Any]:
        """导出为纯 JSON 可序列化的 dict（Enum 转 value、dataclass 转 dict）。"""
        result = _to_plain(
            {
                "scenario_name": self.scenario_name,
                "seed": self.seed,
                "effects": self.effects,
                "run_segments": self.run_segments,
                "violations": self.violations,
                "warnings": self.warnings,
            }
        )
        return dict(result)

    def to_json(self) -> str:
        """导出为确定性 JSON 字符串（字段顺序固定、无 wall clock）。"""
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _format_effect(effect: EffectRecord) -> str:
        fault = effect.fault.value if effect.fault is not None else "-"
        branch = effect.branch_id or "-"
        return (
            f"[{effect.effect_id}] {effect.effect_type} key={effect.business_key} "
            f"attempt={effect.attempt} status={effect.status.value} fault={fault} "
            f"run={effect.run_id or '-'} thread={effect.thread_id or '-'} "
            f"checkpoint={effect.checkpoint_id or '-'} branch={branch}"
        )


def _to_plain(obj: Any) -> Any:
    """递归地把 dataclass / Enum / tuple 转为纯 JSON 可序列化结构。"""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Mapping):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]
    return obj
