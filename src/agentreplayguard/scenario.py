"""Scenario：装配 store/clock/injector/invariants，管理生命周期。"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

from .clock import LogicalClock, counter_id
from .effects import EffectStore
from .errors import ScenarioConfigError, ScenarioStateError
from .faults import FaultInjector, FaultPlan
from .guard import EffectGuard
from .invariants import Invariant, Violation
from .report import RunSegment, ScenarioReport


class ScenarioState(Enum):
    CREATED = "created"
    RUNNING = "running"
    FINISHED = "finished"


class Scenario:
    """一次可复现实验的根对象，持有运行期状态。"""

    def __init__(
        self,
        name: str,
        *,
        seed: int = 0,
        faults: FaultPlan | None = None,
        invariants: Sequence[Invariant] = (),
    ) -> None:
        if not name:
            raise ScenarioConfigError("Scenario.name must be non-empty")
        if len(name) > 80:
            raise ScenarioConfigError("Scenario.name must be <= 80 characters")
        if not isinstance(seed, int):
            raise ScenarioConfigError("Scenario.seed must be an int")

        self._name = name
        self._seed = seed
        self._faults = faults if faults is not None else FaultPlan()
        self._invariants = tuple(invariants)
        self._validate_invariant_names()

        self._clock = LogicalClock()
        self._store = EffectStore()
        self._injector = FaultInjector(self._faults, seed)

        self._state = ScenarioState.CREATED
        self._run_segments: list[RunSegment] = []
        self._extra_warnings: list[str] = []
        self._report: ScenarioReport | None = None

        self._run_counter = 0
        self._run_id: str | None = None
        self._thread_id: str | None = None
        self._checkpoint_id: str | None = None

        self._guard = EffectGuard(
            self._store,
            self._clock,
            self._injector,
            run_context=self._current_run_context,
            check_state=self._ensure_running,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def effects(self) -> EffectStore:
        return self._store

    def guard(self) -> EffectGuard:
        return self._guard

    def finish(self) -> ScenarioReport:
        if self._report is not None:
            return self._report
        if self._state is ScenarioState.CREATED:
            self._state = ScenarioState.RUNNING
        self._state = ScenarioState.FINISHED

        violations: list[Violation] = []
        for invariant in self._invariants:
            violations.extend(invariant.check(self._store))

        report = ScenarioReport(
            scenario_name=self._name,
            seed=self._seed,
            effects=self._store.records,
            run_segments=tuple(self._run_segments),
            violations=tuple(violations),
            warnings=tuple(self._warnings()),
        )
        self._report = report
        return report

    # 内部接口：供 EffectGuard 与 LangGraphAdapter 使用
    def _validate_invariant_names(self) -> None:
        seen: set[str] = set()
        for invariant in self._invariants:
            if invariant.name in seen:
                raise ScenarioConfigError(f"duplicate invariant name: {invariant.name}")
            seen.add(invariant.name)

    def _ensure_running(self) -> None:
        if self._state is ScenarioState.FINISHED:
            raise ScenarioStateError("scenario is FINISHED and cannot be used")
        if self._state is ScenarioState.CREATED:
            self._state = ScenarioState.RUNNING

    def _current_run_context(self) -> tuple[str | None, str | None, str | None]:
        return (self._run_id, self._thread_id, self._checkpoint_id)

    def _begin_run(self, thread_id: str, checkpoint_id: str | None) -> str:
        self._run_counter += 1
        run_id = counter_id("run", self._run_counter, 4)
        self._run_id = run_id
        self._thread_id = thread_id
        self._checkpoint_id = checkpoint_id
        return run_id

    def _end_run(self) -> None:
        self._run_id = None
        self._thread_id = None
        self._checkpoint_id = None

    def _add_run_segment(self, segment: RunSegment) -> None:
        self._run_segments.append(segment)

    def _tick(self) -> int:
        return self._clock.tick()

    def _warn(self, message: str) -> None:
        self._extra_warnings.append(message)

    def _warnings(self) -> list[str]:
        warnings: list[str] = []
        if not self._invariants:
            warnings.append("no invariants declared; scenario passes by default")
        warnings.extend(self._extra_warnings)
        return warnings
