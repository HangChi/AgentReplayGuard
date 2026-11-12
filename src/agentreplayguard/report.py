"""运行报告：RunSegment、GraphRun 与 ScenarioReport。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
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

    @staticmethod
    def _format_effect(effect: EffectRecord) -> str:
        fault = effect.fault.value if effect.fault is not None else "-"
        return (
            f"[{effect.effect_id}] {effect.effect_type} key={effect.business_key} "
            f"attempt={effect.attempt} status={effect.status.value} fault={fault} "
            f"run={effect.run_id or '-'} thread={effect.thread_id or '-'} "
            f"checkpoint={effect.checkpoint_id or '-'}"
        )
