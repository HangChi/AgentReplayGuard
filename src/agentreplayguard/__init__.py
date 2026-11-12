"""公开导出面（见 specs/001-effect-safety-testing/contracts/public-api.md）。

`LangGraphAdapter` 不在此导出，需从 `agentreplayguard.adapters.langgraph` 单独导入，
以保证核心包在未安装 langgraph 时可导入。
"""

from __future__ import annotations

from .effects import EffectRecord, EffectStatus, EffectStore, EffectView
from .errors import (
    EffectSafetyError,
    PartialSuccessError,
    ScenarioConfigError,
    ScenarioStateError,
    ServiceError,
    UnsupportedGraphError,
)
from .faults import FaultKind, FaultPlan, FaultRule
from .guard import EffectGuard
from .invariants import (
    CustomInvariant,
    Invariant,
    MaxEffectCount,
    NoDuplicateEffects,
    Violation,
)
from .report import GraphRun, RunInputKind, RunSegment, ScenarioReport
from .scenario import Scenario

__all__ = [
    "CustomInvariant",
    "EffectGuard",
    "EffectRecord",
    "EffectSafetyError",
    "EffectStatus",
    "EffectStore",
    "EffectView",
    "FaultKind",
    "FaultPlan",
    "FaultRule",
    "GraphRun",
    "Invariant",
    "MaxEffectCount",
    "NoDuplicateEffects",
    "PartialSuccessError",
    "RunInputKind",
    "RunSegment",
    "Scenario",
    "ScenarioConfigError",
    "ScenarioReport",
    "ScenarioStateError",
    "ServiceError",
    "UnsupportedGraphError",
    "Violation",
]
