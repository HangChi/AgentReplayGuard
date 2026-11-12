"""异常体系：公开异常类型与继承关系。

继承关系是公开契约的一部分（见 contracts/public-api.md），任何变更需同步更新契约测试。
"""

from __future__ import annotations


class EffectSafetyError(AssertionError):
    """不变量违规：`ScenarioReport.assert_clean()` 在存在违规时抛出。"""


class ScenarioConfigError(ValueError):
    """场景 / 规则 / 参数哈希等配置非法。"""


class ScenarioStateError(RuntimeError):
    """场景在 FINISHED 之后被继续使用。"""


class UnsupportedGraphError(RuntimeError):
    """图不具备所需 API，或检测到不支持的图形态（如并行 fan-out）。"""


class ServiceError(Exception):
    """模拟服务端 5xx 错误，携带 HTTP 状态码。"""

    def __init__(self, status: int, message: str = "") -> None:
        self.status = status
        super().__init__(message or f"service error {status}")


class PartialSuccessError(Exception):
    """部分成功故障：主操作已提交，但后续步骤失败。"""
