"""pytest 测试配置。

`pytester` 用于在本仓库内验证「嵌套 pytest 运行」的语义——013 自动断言必须能证明
「用户漏写断言时测试确实失败」，这只能在真实 pytest 运行中观察。
"""

from __future__ import annotations

pytest_plugins = ["pytester"]
