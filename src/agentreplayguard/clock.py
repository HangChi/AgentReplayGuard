"""逻辑时钟与确定性 ID 生成。

不依赖 wall clock、UUID 或对象地址，保证同一场景与 seed 下轨迹可复现。
"""

from __future__ import annotations


class LogicalClock:
    """单调递增的逻辑时钟，从 0 开始。"""

    def __init__(self) -> None:
        self._now = 0

    def now(self) -> int:
        """当前逻辑时间。"""
        return self._now

    def tick(self) -> int:
        """推进一个单位并返回新的逻辑时间。"""
        self._now += 1
        return self._now


def counter_id(prefix: str, value: int, width: int) -> str:
    """生成确定性的零填充序号 ID，如 counter_id("eff", 1, 6) -> "eff-000001"。"""
    return f"{prefix}-{value:0{width}d}"
