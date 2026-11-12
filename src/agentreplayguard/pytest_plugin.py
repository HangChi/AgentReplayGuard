"""pytest 插件入口：提供 `replayguard` fixture。

通过 `pyproject.toml` 的 `[project.entry-points.pytest11]` 自动注册；
插件不执行任何全局补丁，仅返回 `Scenario` 构造器。
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from .scenario import Scenario


@pytest.fixture
def replayguard() -> Callable[..., Scenario]:
    """返回 `Scenario` 构造器；每次调用生成全新场景实例。"""
    return Scenario
